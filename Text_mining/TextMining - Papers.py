import os
import pdfplumber
import inspect
from Utils import *
from NameExtraction import *

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
paper_folder = os.path.join(currentdir, 'Papers')


def remove_empty_boxes(groups, segments):
    output = {}
    for gr, seg in zip(groups, segments):
        if seg is None or gr is None:
            continue
        del_groups = [list(gr.keys())[i] for i in range(len(gr)) if len(seg.sentences[i]) == 0]
        for k in del_groups:
            del gr[k]
        output = {**output, **gr}
    return output


def retrieve_body(total, stats):
    body = total.filter(by=stats.get_struct(n=0)[0], targ=FLAGS.body).dbscan(min_samples=4)
    b_boxes = body.divide_by_labels(min_n=15)
    for g in b_boxes:
        lines = b_boxes[g].find_lines(min_on_line=10)
        body.get_sentences(by_lines=lines, bounds=b_boxes[g].boundaries,
                           flag=FLAGS.body, take_from=total)
    return body, b_boxes


def retrieve_title(total, stats):
    if stats.title_font is not None:
        title = total.filter(by=stats.title_font, targ=FLAGS.title)
        g_title = list(title.divide_by_labels(min_n=3).values())[0]
        lines = g_title.find_lines(min_on_line=10)
        title.get_sentences(by_lines=lines, bounds=g_title.boundaries,
                            flag=FLAGS.title, take_from=total)
        t_boxes = {FLAGS.title: g_title}
    else:
        title = total.dbscan(min_samples=4, consider_fonts=True)
        title.flag = FLAGS.title
        t_boxes = title.divide_by_labels(min_n=5, skip_from=9)
        candidates = []
        for g in t_boxes:
            lines = t_boxes[g].find_lines(min_on_line=8)
            mean_x = t_boxes[g].boundaries[1] + t_boxes[g].boundaries[3] / 2
            c_loss = math.fabs((stats.max_width + stats.min_width) / 2 - mean_x)
            candidates.append((c_loss, lines, t_boxes[g]))
        candidates = sorted(candidates, key=lambda x: x[0])
        candidates = [el for el in candidates if 6 < len(el[2]) < 80]
        t_boxes = None
        for i in range(0, len(candidates)):
            title.get_sentences(by_lines=candidates[i][1], bounds=candidates[i][2].boundaries,
                                flag=FLAGS.title, take_from=total, test=True)
            if len(title.test_s) > 0:
                title.get_sentences(by_lines=candidates[i][1], bounds=candidates[i][2].boundaries,
                                    flag=FLAGS.title, take_from=total)
                t_boxes = {FLAGS.title: candidates[i][2]}
                break
    title.to_string(print_=True)
    return title, t_boxes


def main():
    with pdfplumber.open(papers_path[pap_index]) as pdf:
        stats = PDF_Stats(pdf, n_pages=5)

        body_text = ''
        for page_n in range(len(pdf.pages)):
            page = pdf.pages[page_n]
            page_title = f'Page {page_n + 1}/{len(pdf.pages)}'
            total = Segment(stats).build_segment(page.chars)

            body, b_boxes = retrieve_body(total, stats)

            title, t_boxes = retrieve_title(total, stats) if page_n == 0 else (None, None)

            groups = remove_empty_boxes(groups=[b_boxes, t_boxes], segments=[body, title])

            body_text += body.to_string(print_=True)

            total.show(title=page_title, show_lines=True, boxes=groups.values())

        names = extract_names(body_text)
        print('------BODY NAMES--------')
        for name in names:
            print('-', name)
        print('------------------------')


if __name__ == '__main__':
    papers = os.listdir(paper_folder)
    papers_path = [os.path.join(paper_folder, el) for el in papers]
    pap_index = 5
    print(f'Analysis on the paper: {papers[pap_index]}')
    main()
