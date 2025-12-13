class Number:
    def __init__(self, str_value):
        self.str_value = str_value
        n_val, ms_str = str_value.split(',')
        self.h, self.m, self.s = n_val.split(":")
        self.h = int(self.h)
        self.m = int(self.m)
        self.s = int(self.s)
        self.ms = int(ms_str)
        self.timestamp = self.get_timestamp()
    
    def get_timestamp(self):
        return self.ms + self.s * 1000 + self.m * 60 * 1000 + self.h * 60 * 60 * 1000

    def add_zeros(self, value):
        if len(str(value)) < 2:
            return "0" + str(value)
        else:
            return str(value)

    def __str__(self):
        return f"{self.add_zeros(self.h)}:{self.add_zeros(self.m)}:{self.add_zeros(self.s)},{self.ms}"
    
    def add_ms(self, ms):
        self.ms += ms
        rest = self.ms // 1000
        self.ms = self.ms % 1000
        self.s += rest
        rest = self.s // 60
        self.s = self.s % 60
        self.m += rest
        rest = self.m // 60
        self.m = self.m % 60
        self.h += rest


class Segment:
    def __init__(self, n1: Number, n2: Number):
        self.n1 = n1
        self.n2 = n2

    def __str__(self):
        return f"{self.n1} --> {self.n2}\n"


def shift_srt_subs(input_file, output_file, ms_to_add, extend=100, extend_s=0):
    """
    File template:
    ...\n
    ...\n
    hh:mm:ss,ooo --> hh:mm:ss,ooo\n
    ...\n
    """

    if extend <= 1:
        raise Exception("Extension only works for percentage values.")

    with open(input_file, 'r', encoding="utf-8", errors="ignore") as file:
        lines = file.readlines()

    new_lines = []
    segments = []
    for line in lines:
        if '-->' in line:
            print("as")
            value_a, value_b = line.replace('\n', '').split(" --> ")
            n1, n2 = Number(value_a), Number(value_b)
            segment = Segment(n1, n2)

            segments.append(segment)
            new_lines.append(segment)
        else:
            new_lines.append(line)

    total_ms = segments[-1].n2.timestamp - segments[0].n1.timestamp
    if extend_s != 0:
        extend = (total_ms + extend_s * 1000) / total_ms * 100
    for s in segments:
        to_add_from_extend = - (100 - extend) / 100 * (s.n1.timestamp - segments[0].n1.timestamp)
        to_add = int(to_add_from_extend + ms_to_add)
        s.n1.add_ms(to_add)
        s.n2.add_ms(to_add)

    with open(output_file, 'w') as file:
        file.writelines([str(x) for x in new_lines])


if __name__ == "__main__":
    input_file = r"C:\Users\shape\Desktop\test.srt"
    output_file = input_file
    shift_srt_subs(input_file, output_file, 0, extend_s=-5)
