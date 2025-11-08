class Number:
    def __init__(self, str_value):
        self.str_value = str_value
        n_val, ms_str = str_value.split(',')
        self.h, self.m, self.s = n_val.split(":")
        self.h = int(self.h)
        self.m = int(self.m)
        self.s = int(self.s)
        self.ms = int(ms_str)

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


def shift_srt_subs(input_file, output_file, ms_to_add):
    """
    File template:
    ...\n
    ...\n
    hh:mm:ss,ooo --> hh:mm:ss,ooo\n
    ...\n
    """

    with open(input_file, 'r') as file:
        lines = file.readlines()

    new_lines = []
    i = 0
    for line in lines:
        i += 1
        if '-->' in line:
            value_a, value_b = line.replace('\n', '').split(" --> ")
            n1, n2 = Number(value_a), Number(value_b)
            n1.add_ms(ms_to_add)
            n2.add_ms(ms_to_add)
            new_lines.append(f"{n1} --> {n2}\n")
        else:
            new_lines.append(line)

    with open(output_file, 'w') as file:
        file.writelines(new_lines)


if __name__ == "__main__":
    input_file = r"D:\Purgatory\.working\Deadpool (2016)\Deadpool (2016).ita.srt"
    output_file = input_file
    shift_srt_subs(input_file, output_file, 1800)
