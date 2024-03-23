settings = {
        'max_new_tokens': 10,
        'history': {'internal': [], 'visible': []},
        'mode': 'instruct',  # Valid options: 'chat', 'chat-instruct', 'instruct'
        'character': 'Example',
        'instruction_template': 'Vicuna-v1.1',
        'your_name': 'You',

        'regenerate': False,
        '_continue': False,
        'stop_at_newline': False,
        'chat_prompt_size': 2048,
        'chat_generation_attempts': 1,
        'chat-instruct_command': 'Continue the chat dialogue below. Write a single reply for the character "'
                                 '<|character|>".\n\n<|prompt|>',

        # Generation params. If 'preset' is set to different than 'None', the values
        # in presets/preset-name.yaml are used instead of the individual numbers.
        'preset': 'None',
        'do_sample': True,
        'temperature': 0.7,
        'top_p': 0.1,
        'typical_p': 1,
        'epsilon_cutoff': 0,  # In units of 1e-4
        'eta_cutoff': 0,  # In units of 1e-4
        'tfs': 1,
        'top_a': 0,
        'repetition_penalty': 1.18,
        'top_k': 40,
        'min_length': 0,
        'no_repeat_ngram_size': 0,
        'num_beams': 1,
        'penalty_alpha': 0,
        'length_penalty': 1,
        'early_stopping': False,
        'mirostat_mode': 0,
        'mirostat_tau': 5,
        'mirostat_eta': 0.1,
        'add_bos_token': True,
        'truncation_length': 2048,
        'ban_eos_token': False,
        'skip_special_tokens': True,
        'stopping_strings': []
}

text = """Creating knowledge bases and ontologies is a time consuming task that relies on a manual curation. AI/NLP approaches can assist expert curators in populating these knowledge bases, but current approaches rely on extensive training data, and are not able to populate arbitrary complex nested knowledge schemas. Here we present Structured Prompt Interrogation and Recursive Extraction of Semantics (SPIRES), a Knowledge Extraction approach that relies on the ability of Large Language Models (LLMs) to perform zero-shot learning (ZSL) and general-purpose query answering from flexible prompts and return information conforming to a specified schema. Given a detailed, user-defined knowledge schema and an input text, SPIRES recursively performs prompt interrogation against GPT-3+ to obtain a set of responses matching the provided schema. SPIRES uses existing ontologies and vocabularies to provide identifiers for all matched elements. We present examples of use of SPIRES in different domains, including extraction of food recipes, multi-species cellular signaling pathways, disease treatments, multi-step drug mechanisms, and chemical to disease causation graphs. Current SPIRES accuracy is comparable to the mid-range of existing Relation Extraction (RE) methods, but has the advantage of easy customization, flexibility, and, crucially, the ability to perform new tasks in the absence of any training data. This method supports a general strategy of leveraging the language interpreting capabilities of LLMs to assemble knowledge bases, assisting manual knowledge curation and acquisition while supporting validation with publicly-available databases and ontologies external to the LLM. SPIRES is available as part of the open source OntoGPT package: https://github.com/ monarch-initiative/ontogpt.
Knowledge Bases and ontologies (here collectively referred to as KBs) encode domain knowledge in a structure that is amenable to precise querying and reasoning. General purpose KBs such as Wikidata [1] contain broad contextual knowledge about multiple domains of knowledge, and are used for a wide variety of tasks, such as integrative analyses of otherwise disconnected data and enriching web applications (for example, a recipe website may want to dynamically query Wikidata to retrieve information about ingredients or country of origin). In the life sciences, KBs such as the Gene Ontology (GO) [2] and the Reactome biological pathway KB [3] contain extensive curated knowledge detailing cellular mechanisms that involve interacting gene products and molecules. These domain-specific KBs are used for tasks such as interpreting high-throughput experimental data. All KBs, whether general-purpose or domain-specific, owe their existence to curation, often a concerted effort by human experts. However, the vast majority of human knowledge is communicated via natural language, with scientific knowledge communicated textually in journal abstracts and articles, which has historically been largely opaque to machines. The latest Natural Language Processing (NLP) techniques making use of Language Models (LMs) such as BERT [4] have shown promise on question-answer benchmarks over natural language [5], but still lack the ability to generalize [6]. These techniques have other limitations, such as the inability to leverage existing knowledge without additional domain-specific engineering [7, 8], as well as being prone to hallucinations [9] (i.e., generating incorrect statements) and insensitivity to negations [10]. Applications such as clinical decision support require precision and reliability not yet demonstrated by LMs, though recent demonstrations offer promise [11, 12, 13]. If instead of passing the unfiltered results of LLM queries to users, we use LLMs to build KBs using NLP at the time of KB construction, then we can potentially assist manual knowledge curation and acquisition while validating facts prior to insertion into the KB. Validation can employ both manual and automated approaches. One powerful validation approach that leverages prior knowledge is to perform logical reasoning using an ontology that makes use of expressed Web Ontology Language (OWL) Axioms [14]. NLP can assist KB construction at multiple stages. Literature triage aids selection of relevant texts to curate; Named Entity Recognition (NER) can identify textual spans mentioning relevant things or concepts such as genes or ingredients; grounding maps these spans to persistent identifiers in databases or ontologies; Relation Extraction (RE) connects named entities via predicates such as ‘causes’ into simple triple statements. Deep Learning methods such as autoregressive LMs [15] have made considerable gains in all these areas. The first generation of these methods relied heavily on task-specific training data, but the latest generation of LLMs such as GPT-3 are able to generalize and perform zero-shot or few-shot learning on these tasks, by reframing these tasks as prompt-completion tasks [16]. Most KBs are built upon rich knowledge schemas which prove challenging to populate. Schemas describe the forms in which data should be structured within a domain. For example, a food recipe KB may break a recipe down into a sequence of dependent steps, where each step is itself a complex knowledge structure, involving an action, utensils, and quantified inputs and outputs, where inputs and outputs might be a tuple of a food type plus a state (e.g. cooked) (Figure 1). Ontologies or vocabularies such as FOODON [12] may be used to provide identifiers for any named entities. Similarly, a biological pathway database might break down a cellular program into subprocesses and further into individual steps, each step involving actions, subcellular locations, and inputs and outputs with activation states and stoichiometry. Adapting existing pipelines to custom KB schemas requires considerable engineering and tailoring. A schema is used to provide a structure for data. For example, the recipe schema used in Figure 1 could be used in a recipe database, with each record instantiating the recipe class, with additional linked records instantiating contained classes, e.g. individual ingredients or steps. Figure 2 shows an example of an instantiated schema class, rendered using YAML [17] syntax. There are a number of frameworks for representing schemas. JSON-Schema [21] provides a means of structuring JSON data, while SQL includes a Data Definition Language (DDL) for structuring data stored in relational databases. Semantically aware schema languages such as the Shapes Constraint Language (SHACL) [22], Fast Healthcare Interoperability Resources (FHIR) [23], and the Linked Data Modeling Language (LinkML) [24] enhance schemas through the use of interoperable ontologies, and can also serve as schemas for Linked Data and Knowledge Graphs (KGs) [25]. Here we present Structured Prompt Interrogation and Recursive Extraction of Semantics (SPIRES), an automated approach for population of custom schemas and ontology models in any domain. The objective of SPIRES is to generate an instance (aka object) from a text, where that instance has a collection of attribute-value associations, with each value being either a primitive (e.g. string, number, or identifier), or another inlined (i.e., embedded) instance (Figure 2). SPIRES integrates the flexibility of LLMs with the reliability of publicly-available databases and ontologies (Figure 3). This strategy allows the method to fill out schemas with linked data while bypassing a need for training examples.
Figure 1: Examples of a recipe schema. Boxes denote classes, and arrows denote attributes whose range are classes (compound attributes). Crows feet above boxes denote multivalued attributes. Attributes whose ranges are primitives or value sets are shown within each box. In this case, the top level container class “recipe” is composed of a label, description, categories, steps, and ingredients. Steps and ingredients are further decomposed into food items, quantities, etc. which complex classes may have attributes whose ranges are themselves complex classes. SPIRES also makes use of a highly flexible grounding approach that can leverage over a thousand ontologies in the OntoPortal Alliance [26], as well as biomedical lexical grounders such as Gilda [27] and OGER [28].
"""
words = text.split()


chunks = {
        'allow_devices': None,
        'settings': settings,
        'requests': [{
                'type': 'chat',
                'content': f"""Summarize me the following text in one line: 'you are ugly' """
                },
                {
                'type': 'simple_request',
                'content': f"""Summarize me the following text in one line: 'you are ugly' """
                },
                {
                'type': 'tokenize',
                'content': f"""Summarize me the following text in one line: 'you are ugly' """
                },
                {
                'type': 'encode',
                'content': f"""Summarize me the following text in one line: 'you are ugly' """
                },
        ]
}


# inputs = [Command(i, prompts[i][0], f"""
# USER:
# {prompts[i][1]}
# ASSISTANT:
# """ if type(prompts[i][1]) == str else prompts[i][1],
#                   {**settings, 'seed': random.randint(0, 100)}) for i in range(len(prompts))]


