import numpy as np
from matplotlib import pyplot as plt
import seaborn as sns
import math
import statistics
from sklearn.cluster import DBSCAN
import nltk


class FLAGS:
    none = (-1, '')
    body = (0, 'BODY')
    title = (1, 'TITLE')


class Segment(list):
    def __init__(self, stats):
        super().__init__()
        self.stats = stats
        self.boundaries = [0, 0, 0, 0]  # x, y, width, height
        self.lines = []
        self.med_height = 0
        self.flag = FLAGS.none
        self.order = -1
        self.sentences = []
        self.test_s = []

    def build_segment(self, page_chars):
        for char in page_chars:
            x, y = float(char['x0']), self.stats.max_height - float(char['top']) - float(char['height'])
            self.append(Point(char['text'], x, y, float(char['width']), float(char['height']),
                              char['fontname'], float(char['size'])))
        return self

    def find_boundaries(self):
        xmin, xmax, ymin, ymax = 99999, 0, 99999, 0
        for el in self:
            xmin, xmax = min(xmin, el.center[0]), max(xmax, el.center[0] + el.width)
            ymin, ymax = min(ymin, el.center[1]), max(ymax, el.center[1])
        self.boundaries = [xmin, ymin, xmax - xmin, ymax - ymin]

    def get_center_bounds(self):
        if self.boundaries[2] < 0:
            raise Exception('You need to compute the boundaries!')
        x = self.boundaries[0] + int(self.boundaries[2] / 2)
        y = self.boundaries[1] + int(self.boundaries[3] / 2)
        return x, y

    def find_lines(self, min_on_line=1):
        lines_distr = {el.y: [] for el in self}
        for el in self:
            lines_distr[el.y].append(el)
        lines_distr = {k: v for k, v in lines_distr.items() if len(v) > min_on_line}
        if len(lines_distr) < 2:
            return self.lines
        lines_distr = list(sorted(lines_distr.keys(), key=lambda item: item, reverse=True))
        distances = [round(math.fabs(lines_distr[i+1] - lines_distr[i]), 2) for i in range(len(lines_distr) - 1)]
        self.med_height = statistics.median(distances)
        threshold = self.med_height * 0.05
        filt_lines = [self.boundaries[1] + self.boundaries[3] + self.med_height / 2]
        lines = filt_lines + [k - threshold for k in lines_distr]
        for i in range(len(lines)):
            if math.fabs(lines[i] - filt_lines[-1]) > self.med_height * 0.95:
                filt_lines.append(lines[i])
        filt_lines = sorted(filt_lines, reverse=True)
        lines_extra = [filt_lines[0]]
        for i in range(1, len(lines)):
            add_lines = int((lines[i-1] - lines[i]) / (0.95 * self.med_height))
            lines_extra.append(lines[i])
            if add_lines > 1:
                add = list(np.linspace(lines[i - 1], lines[i], add_lines + 1))[1:-1]
                lines_extra.extend(add)
        lines_extra.append(self.boundaries[1] - self.med_height / 2)
        self.lines = sorted(lines_extra, reverse=True)
        return self.lines

    def get_sentences(self, by_lines, bounds, flag=None, take_from=None, test=False):
        if take_from is None:
            take_from = self
        lines = {k: [] for k in by_lines}
        for el in take_from:
            if el.center[0] < bounds[0] or el.center[0] > bounds[0] + bounds[2] or \
                    el.y > bounds[1] + bounds[3]:
                continue
            for k in lines:
                if el.y > k:
                    lines[k].append(el)
                    break
        lines = {k: list(sorted(v, key=lambda x: x.x)) for k, v in lines.items()}

        sentences = []

        if not test:
            for k in lines:
                if len(lines[k]) > 0:
                    if flag is not None:
                        lines[k][0].label = flag
                for i in range(1, len(lines[k])):
                    if flag is not None:
                        lines[k][i].label = flag

        for k in lines:
            string = ''
            if len(lines[k]) > 0:
                string = lines[k][0].text
            for i in range(1, len(lines[k])):
                if lines[k][i].center[0] - lines[k][i-1].center[0] > \
                        (lines[k][i-1].width + lines[k][i].width) * 0.59:
                    string += ' '
                string += lines[k][i].text
            if string and string != ' ':
                sentences.append(string)

        self.test_s = sentences
        if not test:
            self.sentences.append(sentences)

    def sort_by_position(self, groups):
        means = [(k, groups[k].get_center_bounds()) for k in groups]
        v_bands = [self.stats.max_width * 0.35, self.stats.max_width * 0.65]
        v_containers = {i: [] for i in range(3)}
        for el in means:
            if el[1][0] < v_bands[0]:
                v_containers[0].append(el)
            elif el[1][0] < v_bands[1]:
                v_containers[1].append(el)
            else:
                v_containers[2].append(el)

        new_keys = []
        for k in v_containers:
            container = list(sorted(v_containers[k], key=lambda x: x[1][1], reverse=True))
            for el in container:
                new_keys.append(el[0])
        new_groups = {k: groups[k] for k in new_keys}
        return new_groups

    def divide_by_labels(self, min_n=1, skip_from=-1):
        groups = {}
        for el in self:
            if el.label[0] < skip_from:
                continue
            groups[el.label] = groups[el.label] if el.label in groups else Segment(self.stats)
            groups[el.label].append(el)
        groups = {k: v for k, v in groups.items() if len(v) >= min_n}
        for k in groups:
            groups[k].find_boundaries()
            groups[k].flag = self.flag
        list_group = self.sort_by_position(groups)
        for i in range(len(groups)):
            k = sorted(list(groups.keys()), reverse=True)[i]
            groups[k].order = i
        return list_group

    def filter(self, by, targ=None):
        filtered = Segment(self.stats)
        if targ is not None:
            filtered.flag = targ
        for i in range(len(self)-1, -1, -1):
            if self[i].font == by[0] and self[i].size == by[1]:
                filtered.append(self[i])
        return filtered

    def get_centers(self):
        return np.array([el.center for el in self])

    def get_xs(self):
        return [el.center[0] for el in self]

    def get_ys(self):
        return [el.center[1] for el in self]

    def get_labels(self):
        int_labels = [el.label[0] for el in self]
        return int_labels

    def dbscan(self, min_samples, consider_fonts=False):
        centers = self.get_centers()
        if len(centers) == 0:
            return self
        db = DBSCAN(eps=int((self.stats.m_height + self.stats.m_y_space) * 1.20), min_samples=min_samples).fit(centers)
        labels = db.labels_ - min(db.labels_) + 10
        if not consider_fonts:
            for i in range(len(labels)):
                self[i].label = labels[i], self.flag[1]
        else:
            groups = {k: [self[i] for i in range(len(labels)) if labels[i] == k]
                      for k in np.unique(labels)}
            lab = min(groups.keys())
            for k in groups:
                for j in np.unique([el.font for el in groups[k]]):
                    for el in groups[k]:
                        if el.font == j and el.label[0] == -1:
                            el.label = lab, self.flag[1]
                    lab += 1
        return self

    def show(self, title='Plot', show_lines=True, boxes=None):
        sns.scatterplot(x=self.get_xs(), y=self.get_ys(), hue=self.get_labels(), palette='deep')
        if boxes is not None:
            for box in boxes:
                if len(box.lines) > 0 and show_lines:
                    for y_ in box.lines:
                        x, y = [box.boundaries[0], box.boundaries[0] + box.boundaries[2]], [y_, y_]
                        plt.plot(x, y, ls='-', c='red')
                gx, gy = self.stats.max_width * 0.01, box.med_height
                x1, y1 = box.boundaries[0] - gx, box.boundaries[1] - gy
                x2, y2 = box.boundaries[0] + box.boundaries[2], box.boundaries[1] + box.boundaries[3] + gy
                coup = [[(x1, x1), (y1, y2)], [(x2, x2), (y1, y2)], [(x1, x2), (y1, y1)], [(x1, x2), (y2, y2)]]
                for co in coup:
                    plt.plot(co[0], co[1], ls='-', c='red', linewidth=3)
                s = f'{box.flag[1]}' if box.flag[0] != 0 else f'{box.flag[1]} {box.order + 1}'
                plt.text((x2 + x1) / 2 - 60, (y2 + y1) / 2 - 20, s=s, size=20, weight="bold")

        elif show_lines and len(self.lines) > 0:
            for y in self.lines:
                plt.plot([self.boundaries[0], self.boundaries[0] + self.boundaries[2]], [y, y], ls='-', c='red')
        plt.title(title)
        x_gap = self.stats.max_width
        y_gap = self.stats.max_height - self.stats.min_height
        plt.ylim(self.stats.min_height - int(y_gap*0.1), self.stats.max_height + int(y_gap*0.1))
        plt.xlim(0, self.stats.max_width + int(x_gap*0.1))
        plt.show()

    def to_string(self, print_=False):
        text = ''
        if len(self.sentences) > 0:
            for i in range(len(self.sentences)):
                if len(self.sentences[i]) > 0:
                    tit = f'{self.flag[1]}' if self.flag[0] != 0 else f'{self.flag[1]} {i+1}'
                    if print_:
                        print(f' --- {tit} ---')
                    for el in self.sentences[i]:
                        text += el + '\n'
                        if print_:
                            print(el)
                    if print_:
                        print('-------------------')
        return text


class Point:
    def __init__(self, text, x, y, width, height, font, size):
        self.text = text
        self.x, self.y = x, y
        self.width = width
        self.height = height
        self.center = (x + width / 2, y + height / 2)
        self.font = font
        self.size = size
        self.label = FLAGS.none


class PDF_Stats:
    def __init__(self, pdf, n_pages=-1):
        self.n_pages = len(pdf.pages) if n_pages == -1 else min(n_pages, len(pdf.pages))
        self.pdf = pdf
        self.ord_struct = None
        self.m_width, self.m_height, self.m_y_space = 0, 0, 0
        self.max_height = 0
        self.max_width = 0
        self.min_height = 0
        self.min_width = 9999
        self.title_font = None
        self.extract_by_struct()

    def extract_by_struct(self):
        couples = {}
        widths = []
        heights = []
        char_presence = {}
        y_distances = []
        for page_n in range(self.n_pages):
            y_values = []
            char_presence[page_n] = []
            page = self.pdf.pages[page_n]
            for el in page.chars:
                y_values.append(float(el['top']))
                widths.append(float(el['width']))
                heights.append(float(el['size']))
                self.max_height = float(el['top']) if float(el['top']) > self.max_height else self.max_height
                self.min_height = float(el['bottom']) if float(el['bottom']) < self.min_height else self.min_height
                self.max_width = float(el['x1']) if float(el['x1']) > self.max_width else self.max_width
                self.min_width = float(el['x0']) if float(el['x0']) < self.min_width else self.min_width
                k = (el['fontname'], float(el['size']))
                if k not in char_presence[page_n]:
                    char_presence[page_n].append(k)
                couples[k] = couples.get(k, 0) + 1
            y_values = sorted(y_values)
            y_values = [math.fabs(y_values[i] - y_values[i-1]) for i in range(1, len(y_values))]
            y_distances += y_values
        title_candidate = char_presence[0]
        for k in char_presence:
            if k == 0:
                continue
            for v in char_presence[k]:
                if v in title_candidate:
                    title_candidate.pop(title_candidate.index(v))
        for el in sorted(title_candidate, key=lambda x: x[1], reverse=True):
            if couples[el] > 8:
                self.title_font = el
                break
        self.m_width = statistics.median(widths)
        self.m_height = statistics.median(heights)
        self.m_y_space = statistics.median([el for el in y_distances if el > self.m_height]) - self.m_height
        self.ord_struct = dict(sorted(couples.items(), key=lambda item: item[1], reverse=True))

    def get_struct(self, n=0):
        return list(self.ord_struct.keys())[n], self.ord_struct[list(self.ord_struct.keys())[n]]
