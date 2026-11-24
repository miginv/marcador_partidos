#!/usr/bin/env python3
"""Pide a Oracle Cloud (capa Always Free, region de la cuenta) la VM del marcador hasta que
haya capacidad. Pensado para un temporizador systemd en nano cada 5 min: cada ejecucion
hace UN intento y sale.
  - Si ya existe la instancia "marcador" (no terminada) no pide otra: solo comprueba que
    este instalada y, si lo esta, desactiva el temporizador.
  - Crea si hace falta la red (VCN + gateway a internet + subred publica) con los puertos
    22 y 80 abiertos.
  - Prueba ARM (A1.Flex 1 OCPU / 6 GB) y, si no hay hueco, AMD (E2.1.Micro).
  - Cuando arranca: IP publica -> /root/.oci/marcador_vm.json y ejecuta relay/instalar_vm.sh
    por ssh (clave /root/.ssh/oracle_marcador).
Credenciales de la API en /root/.oci/config (nunca en el repo)."""
import json
import os
import subprocess
import sys
import time

import oci

NOMBRE = "marcador"
CLAVE_SSH = "/root/.ssh/oracle_marcador"
ESTADO = "/root/.oci/marcador_vm.json"
INSTALADOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instalar_vm.sh")
TEMPORIZADOR = "oracle-crear-vm.timer"
FORMAS = [("VM.Standard.A1.Flex", {"ocpus": 1, "memory_in_gbs": 6}),
          ("VM.Standard.E2.1.Micro", None)]

cfg = oci.config.from_file()
COMP = cfg["tenancy"]
idn = oci.identity.IdentityClient(cfg)
net = oci.core.VirtualNetworkClient(cfg)
cmp = oci.core.ComputeClient(cfg)


def log(*a):
    print(time.strftime("%d/%m %H:%M:%S"), *a, flush=True)


def red():
    """Subred publica del marcador (la crea si no existe). Devuelve el OCID."""
    vcns = [v for v in net.list_vcns(COMP).data if v.lifecycle_state == "AVAILABLE"]
    vcn = next((v for v in vcns if v.display_name == "vcn-marcador"), None) or (vcns[0] if vcns else None)
    if vcn is None:
        vcn = net.create_vcn(oci.core.models.CreateVcnDetails(
            compartment_id=COMP, display_name="vcn-marcador", cidr_blocks=["10.0.0.0/16"],
            dns_label="marcador")).data
        oci.wait_until(net, net.get_vcn(vcn.id), "lifecycle_state", "AVAILABLE")
        log("[RED] VCN creada")
    subs = [s for s in net.list_subnets(COMP, vcn_id=vcn.id).data
            if s.lifecycle_state == "AVAILABLE" and not s.prohibit_public_ip_on_vnic]
    if subs:
        sub = subs[0]
    else:
        igws = net.list_internet_gateways(COMP, vcn_id=vcn.id).data
        igw = igws[0] if igws else net.create_internet_gateway(oci.core.models.CreateInternetGatewayDetails(
            compartment_id=COMP, vcn_id=vcn.id, is_enabled=True, display_name="igw-marcador")).data
        net.update_route_table(vcn.default_route_table_id, oci.core.models.UpdateRouteTableDetails(
            route_rules=[oci.core.models.RouteRule(destination="0.0.0.0/0", network_entity_id=igw.id)]))
        sub = net.create_subnet(oci.core.models.CreateSubnetDetails(
            compartment_id=COMP, vcn_id=vcn.id, cidr_block="10.0.0.0/24", display_name="subnet-marcador",
            dns_label="pub", prohibit_public_ip_on_vnic=False)).data
        oci.wait_until(net, net.get_subnet(sub.id), "lifecycle_state", "AVAILABLE")
        log("[RED] subred publica creada")
    abrir_puertos(sub)
    return sub.id


def abrir_puertos(sub):
    """Entrada TCP 22 y 80 desde cualquier sitio en las listas de seguridad de la subred."""
    for sl_id in sub.security_list_ids:
        sl = net.get_security_list(sl_id).data
        reglas = list(sl.ingress_security_rules)
        tiene = {r.tcp_options.destination_port_range.min for r in reglas
                 if r.protocol == "6" and r.tcp_options and r.tcp_options.destination_port_range}
        nuevas = [oci.core.models.IngressSecurityRule(
            protocol="6", source="0.0.0.0/0",
            tcp_options=oci.core.models.TcpOptions(
                destination_port_range=oci.core.models.PortRange(min=p, max=p)))
            for p in (22, 80) if p not in tiene]
        if nuevas:
            net.update_security_list(sl_id, oci.core.models.UpdateSecurityListDetails(
                ingress_security_rules=reglas + nuevas, egress_security_rules=sl.egress_security_rules))
            log("[RED] puertos abiertos:", [r.tcp_options.destination_port_range.min for r in nuevas])


def imagen(forma):
    imgs = cmp.list_images(COMP, operating_system="Canonical Ubuntu", operating_system_version="24.04",
                           shape=forma, sort_by="TIMECREATED", sort_order="DESC").data
    imgs = [i for i in imgs if "Minimal" not in i.display_name]
    return imgs[0].id if imgs else None


def instancia():
    for i in cmp.list_instances(COMP, display_name=NOMBRE).data:
        if i.lifecycle_state not in ("TERMINATED", "TERMINATING"):
            return i
    return None


def ip_publica(inst):
    for a in cmp.list_vnic_attachments(COMP, instance_id=inst.id).data:
        v = net.get_vnic(a.vnic_id).data
        if v.public_ip:
            return v.public_ip
    return None


def pedir(sub_id):
    ad = idn.list_availability_domains(COMP).data[0].name
    clave = open(CLAVE_SSH + ".pub").read().strip()
    for forma, conf in FORMAS:
        img = imagen(forma)
        if not img:
            log("[VM] sin imagen para", forma)
            continue
        det = oci.core.models.LaunchInstanceDetails(
            compartment_id=COMP, availability_domain=ad, display_name=NOMBRE, shape=forma,
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(**conf) if conf else None,
            source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=img),
            create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=sub_id, assign_public_ip=True),
            metadata={"ssh_authorized_keys": clave})
        try:
            inst = cmp.launch_instance(det).data
            log("[VM] creada", forma, inst.id)
            return inst
        except oci.exceptions.ServiceError as e:
            if e.status in (500, 429) or "capacity" in str(e.message).lower():
                log("[VM] sin capacidad:", forma, e.status)
                continue
            raise
    return None


def instalar(ip):
    ssh = ["ssh", "-i", CLAVE_SSH, "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10",
           "ubuntu@" + ip]
    for _ in range(30):                       # la VM tarda en aceptar ssh
        if subprocess.run(ssh + ["true"], capture_output=True).returncode == 0:
            break
        time.sleep(10)
    with open(INSTALADOR, "rb") as f:
        r = subprocess.run(ssh + ["bash -s"], stdin=f, capture_output=True, timeout=900)
    log("[INSTALAR]", r.returncode, r.stdout.decode()[-300:], r.stderr.decode()[-300:])
    return r.returncode == 0


def main():
    inst = instancia()
    if inst is None:
        inst = pedir(red())
        if inst is None:
            return 2                           # sin capacidad: el temporizador lo vuelve a intentar
    oci.wait_until(cmp, cmp.get_instance(inst.id), "lifecycle_state", "RUNNING", max_wait_seconds=900)
    ip = ip_publica(inst)
    log("[VM] en marcha", inst.shape, ip)
    est = {}
    if os.path.exists(ESTADO):
        est = json.load(open(ESTADO))
    est.update({"id": inst.id, "forma": inst.shape, "ip": ip})
    json.dump(est, open(ESTADO, "w"), indent=1)
    if not est.get("instalado") and ip and instalar(ip):
        est["instalado"] = time.strftime("%F %T")
        json.dump(est, open(ESTADO, "w"), indent=1)
    if est.get("instalado"):
        subprocess.run(["systemctl", "disable", "--now", TEMPORIZADOR])
        log("[FIN] instalado en", ip, "- temporizador desactivado")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except oci.exceptions.ServiceError as e:
        log("[ERROR]", e.status, e.code, e.message)
        sys.exit(1)
