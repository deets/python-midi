import midi
import pprint
x = midi.FileReader()
with open('mary.mid', "rb") as f:
    p = x.read(f)
    print(p)

