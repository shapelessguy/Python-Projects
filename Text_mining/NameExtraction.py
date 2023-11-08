from Utils import *


def extract_names(texts, download=False):
    output = []
    to_replace = ['\n', ':', '-', ')', '(', '/', '\ '[0], '[', ']', '"', "'", '–']
    for sign in to_replace:
        texts = texts.replace(sign, '')
    if download:
        nltk.download('all')
    tokenizer = nltk.RegexpTokenizer('\w+|\,')
    filtered = tokenizer.tokenize(texts)

    cong = ['e', 'ed', 'o', 'od', ',']
    titles = ['signor', 'signore', 'signorina', 'signorino', 'dottor', 'dottore', 'dottoressa', 'professor',
              'professore', 'professoressa', 'onorevole', 'principe', 'principessa', 'don', 'conte', 'duca',
              'duchessa', 'magnifico', 'senatore', 'senatrice', 'maestro', 'maestra', 'ingegnere', 'ingegner',
              'avvocato', 'avvocatessa', 'architetto', 'deputato', 'deputata', 'amministratore', 'ministro',
              'ministra', 'sindaco',
              ]

    stemmer = nltk.stem.SnowballStemmer(language='italian')
    words_toStem = filtered
    words_toStem = {i: stemmer.stem(words_toStem[i]) for i in range(len(words_toStem))}
    sign_index = [k for k, v in words_toStem.items() if v in titles]
    pos_tagged = nltk.pos_tag(filtered)

    pos_tagged = [(el[0], el[1]) if el[0] not in cong else (el[0], 'CC') for el in pos_tagged]

    all_names = []
    for i in sign_index:
        names = []
        j = i + 1
        while pos_tagged[j][1] == 'CC' or pos_tagged[j][1] == 'NNP':
            if pos_tagged[j][1] == 'NNP':
                if pos_tagged[j-1][1] == 'CC' or len(names) == 0:
                    names.append(pos_tagged[j][0])
                else:
                    names[-1] = names[-1] + ' ' + pos_tagged[j][0]
            j += 1
        all_names.append(names)

    for l in all_names:
        output.extend(l)
    return output
