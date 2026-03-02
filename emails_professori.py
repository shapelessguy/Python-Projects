class lang:
    eng = "eng"
    ita = "ita"


topics = [
    # Da ricontattare in Estate (01.01.26), non si sa quando lo attiverà
    [True, "domenico.amalfitano@unina.it", "Prof. Amalfitano", "Methodologies and Tools for conducting Systematic Literature Reviews and Systematic Mapping Studies", 3, lang.ita],
    
    [False, "anna.corazza@unina.it", "Prof. Corazza", "Machine Learning for Science and Engineering Research", 5, lang.ita],
    
    # Mi fa sapere (01.03.26). Da ricontattare in estate
    [True, "Giancarlo.sperli@unina.it", "Prof. Sperlì", "Big Data Architecture and Analytics", 5, lang.ita],
    
    [False, "pierluigi.rippa@unina.it", "Prof. Rippa", "Innovation and Entrepreneurship", 3, lang.ita],
    
    # 24.06 - 03.07 Si può fare online!
    [False, "teresa.crisci2@unina.it", "Prof. Teresa", "Nanotechnology for Materials and Devices in Microelectronics and Photonics", 3, lang.ita],
    
    # Verso Settembre. Ricontattare in estate
    [True, "giampaolo.bovenzi@unina.it", "Dr. Bovenzi", "Practical Network Intrusion Detectionwith Machine Learning and Generative AI", 4, lang.ita],
    
    [False, "salvatore.barone@unipegaso.it", "Prof. Barone", "Safety Critical Systems for Railway Traffic Management", 4, lang.ita],
    
    # Probabilmente verso fine anno (01.03.26), ma forse non da remoto. Da ricontattare in estate
    [True, "pietro.liguori@unina.it", "Dr. Liguori", "AI Code Generation: Foundations, Evaluation, and Security", 3, lang.ita],
    
    [False, "alfredo.cuzzocrea@unical.it", "Prof. Cuzzocrea", "Advanced Models and Algorithms for Managing, Querying and Analyzing Big Multidimensional Data", 4, lang.ita],
    
    # Niente da remoto
    [False, "lucio.franzese@unina.it", "Prof. Franzese", "La Scienza moderna e il problema della disciplina giuridica dell'IA", 6, lang.ita],
    
    [False, "massimo.rosamilia@unina.it", "Dr. Rosamilia", "Cooperative and Non Cooperative Localization Systems", 3, lang.ita],
    
    # Corso non esiste più
    [False, "olivier.sename@grenoble-inp.fr", "Prof. Sename", "The Linear Parameter Varying approach: theory and application", 4, lang.eng],
    
    [False, "silvestro.micera@epfl.ch", "Prof. Micera", "Design and control of robotic prostheses", 4, lang.eng],
    
    [False, "vincenzoromano.marrazzo@unina.it", "Dr. Marrazzo", "Fiber optic sensing and optoelectronic circuits: design and application", 4, lang.ita],
    
    # Niente per quest anno. Forse anno prossimo
    [False, "raffaele.dellacorte2@unina.it", "Prof. Della Corte", "IoT Data Analysis", 4, lang.ita],
    
    [False, "andrea.apicella@unina.it", "Dr. Apicella", "Using Deep Learning properly", 4, lang.ita],
    
    [False, "gennaro.dimeo@unina.it", "Dr. Di Meo", "Design methodologies for digital circuits and systems oriented to FPGA", 2.4, lang.ita],
    
    [False, "ilaria.matacena@unina.it", "Dr. Matacena", "SOLAR CELLS: MODELLING AND APPLICATIONS", 4, lang.ita],
    
    [False, "adriano.masone@unina.it", "Dr. Masone", "Operational Research: Mathematical Modelling, Methods and Software Tools for Optimization Problems", 4, lang.ita],
    
    [False, "mario.barbareschi@unina.it", "Prof. Barbareschi", "Industrial Embedded Systems Design with the ARM Architecture", 4, lang.ita],
    
    [False, "attaianese@unicas.it", "Prof. Attuaianese", "Advanced Modelling and Control of Energy Storage Systems, Power Converters and Electrical Drives", 6, lang.ita],
]


template_ita = """
Gentile __NAME__

La contatto circa il suo esame "__EXAM__" da __CREDITS__ crediti.
Sono uno studente PhD presso Unina e quest'anno sarò fuori Italia per l'intero anno.

Vorrei gentilmente sapere se il corso è ancora attivo, quando inizierà e se ci fosse la possibilità di seguirlo da remoto.
La discussione sarebbe chiaramente sostenuta in presenza, ma necessiterei di materiale didattico qualora possibile.

Grazie in anticipo per la risposta.

Cordiali saluti,
Claudio Ciano
"""

template_eng = """
Dear __NAME__,

I am contacting you regarding your course "__EXAM__" worth __CREDITS__ credits.
I am a PhD student at the University of Naples and this year I will be outside Italy for the entire year.

I would kindly like to know whether the course is still active, when it will begin, and whether it might be possible to attend it remotely.
The final exam would, of course, be taken in person, but I would need access to the course materials if possible.

Thank you in advance for your response.

Kind regards,
Claudio Ciano
"""


for t in topics:
    if not t[0]:
        print("\n" + t[1])
        print("Esame dottorato")
        template = template_ita if t[5] == lang.ita else template_eng
        print(template.replace("__NAME__", t[2]).replace("__EXAM__", t[3]).replace("__CREDITS__", str(t[4])))