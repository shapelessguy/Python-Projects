test = [
    (1, 6),
    (0, 7),
    (2, 3),
    (3, 4),
    (4, 3),
    (2, 4),
]


for t in test:
    fitness = 80 / (t[0] + 0.1) + t[1] ** 2
    print(f'repeat_idx: {t[0]}  debit: {t[1]}  -> fitness: {fitness}')
