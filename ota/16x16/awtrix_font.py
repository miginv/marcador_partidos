FONT = {
    ' ': b"\x00",                               # space
    'º': b"\x80\x00\x00\x00\x00",        # º
    '!': b"\x80\x80\x80\x00\x80",       # exclam
    '"': b"\xa0\xa0",                         # quotedbl
    '#': b"\xa0\xe0\xa0\xe0\xa0",       # numbersign
    '$': b"\x60\xc0\x60\xc0\x40",       # dollar
    '%': b"\xa0\x20\x40\x80\xa0",       # percent
    '&': b"\xc0\xc0\xe0\xa0\x60",       # ampersand
    "'": b"\x80\x80",                         # quotesingle
    '(': b"\x40\x80\x80\x80\x40",       # parenleft
    ')': b"\x80\x40\x40\x40\x80",       # parenright
    '*': b"\xa0\x40\xa0",                   # asterisk
    '+': b"\x40\xe0\x40",                   # plus
    ',': b"\x40\x80",                         # comma
    '-': b"\x00\x00\xe0\x00\x00",       # hyphen
    '.': b"\x80",                               # period
    '/': b"\x20\x20\x40\x80\x80",       # slash
    '0': b"\xe0\xa0\xa0\xa0\xe0",       # zero
    '1': b"\x40\xc0\x40\x40\xe0",       # one
    '2': b"\xe0\x20\xe0\x80\xe0",       # two
    '3': b"\xe0\x20\xe0\x20\xe0",       # three
    '4': b"\xa0\xa0\xe0\x20\x20",       # four
    '5': b"\xe0\x80\xe0\x20\xe0",       # five
    '6': b"\xe0\x80\xe0\xa0\xe0",       # six
    '7': b"\xe0\x20\x20\x20\x20",       # seven
    '8': b"\xe0\xa0\xe0\xa0\xe0",       # eight
    '9': b"\xe0\xa0\xe0\x20\xe0",       # nine
    ':': b"\x00\x80\x00\x80\x00",                   # colon
    ';': b"\x40\x00\x40\x80",             # semicolon
    '<': b"\x20\x40\x80\x40\x20",       # less
    '=': b"\xe0\x00\xe0",                   # equal
    '>': b"\x80\x40\x20\x40\x80",       # greater
    '?': b"\xe0\x20\x40\x00\x40",       # question
    '@': b"\x40\xa0\xe0\x80\x60",       # at
    'A': b"\xc0\xa0\xe0\xa0\xa0",  # [33]  0x41 A
    'B': b"\xc0\xa0\xc0\xa0\xc0",  # [34]  0x42 B
    'C': b"\x40\xa0\x80\xa0\x40",  # [35]  0x43 C
    'D': b"\xc0\xa0\xa0\xa0\xc0",  # [36]  0x44 D
    'E': b"\xe0\x80\xe0\x80\xe0",  # [37]  0x45 E
    'F': b"\xe0\x80\xe0\x80\x80",  # [38]  0x46 F
    'G': b"\x60\x80\xa0\xa0\x60",  # [39]  0x47 G
    'H': b"\xa0\xa0\xe0\xa0\xa0",  # [40]  0x48 H
    'I': b"\x80\x80\x80\x80\x80",  # [41]  0x49 I
    'J': b"\x20\x20\x20\xa0\x40",  # [42]  0x4A J
    'K': b"\xa0\xa0\xc0\xa0\xa0",  # [43]  0x4B K
    'L': b"\x80\x80\x80\x80\xe0",  # [44]  0x4C L
    'M': b"\x88\xd8\xa8\x88\x88",  # [45]  0x4D M
    'N': b"\x90\xd0\xb0\x90\x90",  # [46]  0x4E N
    'O': b"\x40\xa0\xa0\xa0\x40",  # [47]  0x4F O
    'P': b"\xe0\xa0\xc0\x80\x80",  # [48]  0x50 P
    'Q': b"\x40\xa0\xa0\xa0\x70",  # [49]  0x51 Q
    'R': b"\xe0\xa0\xc0\xa0\xa0",  # [50]  0x52 R
    'S': b"\xe0\x80\xe0\x20\xe0",  # [51]  0x53 S
    'T': b"\xe0\x40\x40\x40\x40",  # [52]  0x54 T
    'U': b"\xa0\xa0\xa0\xa0\xe0",  # [53]  0x55 U
    'V': b"\xa0\xa0\xa0\xa0\x40",  # [54]  0x56 V
    'W': b"\x88\x88\x88\xa8\x50",  # [55]  0x57 W
    'X': b"\xa0\xa0\x40\xa0\xa0",  # [56]  0x58 X
    'Y': b"\xa0\xa0\xe0\x20\xc0",  # [57]  0x59 Y
    'Z': b"\xe0\x20\x40\x80\xe0",  # [58]  0x5A Z
     '[': b"\xe0\x80\x80\x80\xe0",  # [59]  0x5B bracketleft
     '\\': b"\x80\x40\x20",             # [60]  0x5C backslash
     ']': b"\xe0\x20\x20\x20\xe0",  # [61]  0x5D bracketright
     '^': b"\x40\xa0",                    # [62]  0x5E asciicircum
     '_': b"\xe0",                          # [63]  0x5F underscore
     '`': b"\x80\x40",                    # [64]  0x60 grave
    'a': b"\xc0\x60\xa0\xe0",        # [65]  0x61 a
    'b': b"\x80\xc0\xa0\xa0\xc0",  # [66]  0x62 b
    'c': b"\x60\x80\x80\x60",        # [67]  0x63 c
    'd': b"\x20\x60\xa0\xa0\x60",  # [68]  0x64 d
    'e': b"\x60\xa0\xc0\x60",        # [69]  0x65 e
    'f': b"\x20\x40\xe0\x40\x40",  # [70]  0x66 f
    'g': b"\x60\xa0\xe0\x20\x40",  # [71]  0x67 g
    'h': b"\x80\xc0\xa0\xa0\xa0",  # [72]  0x68 h
    'i': b"\x80\x00\x80\x80\x80",  # [73]  0x69 i
    'j': b"\x20\x00\x20\x20\xa0\x40",  # [74]  0x6A j
    'k': b"\x80\xa0\xc0\xc0\xa0",  # [75]  0x6B k
    'l': b"\xc0\x40\x40\x40\xe0",  # [76]  0x6C l
    'm': b"\xe0\xe0\xe0\xa0",        # [77]  0x6D m
    'n': b"\xc0\xa0\xa0\xa0",        # [78]  0x6E n
    'o': b"\x40\xa0\xa0\x40",        # [79]  0x6F o
    'p': b"\xc0\xa0\xa0\xc0\x80",  # [80]  0x70 p
    'q': b"\x60\xa0\xa0\x60\x20",  # [81]  0x71 q
    'r': b"\x60\x80\x80\x80",        # [82]  0x72 r
    's': b"\x60\xc0\x60\xc0",        # [83]  0x73 s
    't': b"\x40\xe0\x40\x40\x60",  # [84]  0x74 t
    'u': b"\xa0\xa0\xa0\x60",        # [85]  0x75 u
    'v': b"\xa0\xa0\xe0\x40",        # [86]  0x76 v
    'w': b"\xa0\xe0\xe0\xe0",        # [87]  0x77 w
    'x': b"\xa0\x40\x40\xa0",        # [88]  0x78 x
    'y': b"\xa0\xa0\x60\x20\x40",  # [89]  0x79 y
    'z': b"\xe0\x60\xc0\xe0",        # [90]  0x7A z
    '{': b"\x60\x40\x80\x40\x60",  # [91]  0x7B braceleft
    '|': b"\x80\x80\x80\x80\x80",  # [92]  0x7C bar
    '}': b"\xc0\x40\x20\x40\xc0",  # [93]  0x7D braceright
    '~': b"\x60\xc0",                    # [94]  0x7E asciitilde
}
