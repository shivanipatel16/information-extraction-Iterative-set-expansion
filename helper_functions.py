import spacy
from spanbert import SpanBERT
from collections import defaultdict

# scripts adopted from https://github.com/gkaramanolakis/SpacySpanBERT

spacy2bert = {
    "ORG": "ORGANIZATION",
    "PERSON": "PERSON",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "DATE": "DATE"
}
bert2spacy = {
    "ORGANIZATION": "ORG",
    "PERSON": "PERSON",
    "LOCATION": "LOC",
    "CITY": "GPE",
    "COUNTRY": "GPE",
    "STATE_OR_PROVINCE": "GPE",
    "DATE": "DATE"
}

def load_nlp_model():
    """
    loads a SpanBERT object with the pretrained_spanbert model
    loads spacy with en_core_web_lg
    :return: spanbert, nlp
    """
    print("Loading necessary libraries; This should take a minute or so ...)")
    spanbert = SpanBERT("./pretrained_spanbert")
    nlp = spacy.load("en_core_web_lg")
    return nlp, spanbert


def get_entities(sentence, entities_of_interest):
    return [(e.text, spacy2bert[e.label_]) for e in sentence.ents if e.label_ in spacy2bert]


def extract_relations(doc, spanbert, desired_relation, entities_of_interest=None, subjects_of_interest=None, objects_of_interest=None, conf=0.7):
    """
    extracts the tuples (subject, object) that have the desired relation and are above the confidence threshold
    :param doc: spacy object with desired text that needs to be extracted from
    :param spanbert: spanbert object
    :param desired_relation: relation that you want to extract like per:employee_of
    :param entities_of_interest: the type of entities that the relation needs
    :param subjects_of_interest: the type of entities that the subject must be
    :param objects_of_interest: the type of entities that the object must be
    :param conf: desired confidence level
    :return: dictionary with (subject, relation, obj) --> confidence value

    """
    num_sentences = len([s for s in doc.sents])
    print("Extracted {} sentences. Processing each sentence one by one to check for presence of right pair of named entity types; if so, will run the second pipeline...".format(num_sentences))
    res = defaultdict(int)
    k = 0

    if subjects_of_interest == None:
        subjects_of_interest = entities_of_interest
    if objects_of_interest == None:
        objects_of_interest = entities_of_interest

    relations_extracted = 0
    sentences_extracted = set()
    for sentence in doc.sents:
        entity_pairs = create_entity_pairs(sentence, entities_of_interest)
        examples = []
        # modification to make sure the examples that get passed to spanbert are of the right entity type
        for ep in entity_pairs:
            if ep[1][1] in subjects_of_interest and ep[2][1] in objects_of_interest:
                examples.append({"tokens": ep[0], "subj": ep[1], "obj": ep[2]})
            if ep[2][1] in subjects_of_interest and ep[1][1] in objects_of_interest:
                examples.append({"tokens": ep[0], "subj": ep[2], "obj": ep[1]})

        if len(examples) != 0:
            preds = spanbert.predict(examples)

            for ex, pred in list(zip(examples, preds)):
                relation = pred[0]

                if relation == desired_relation:

                    relations_extracted += 1
                    sentences_extracted.add(k)
                    print("\n\t\t=== Extracted Relation ===")
                    print("\t\tTokens: {}".format(ex['tokens']))
                    subj = ex["subj"][0]
                    obj = ex["obj"][0]
                    confidence = pred[1]
                    print("\t\tRelation: {} (Confidence: {:.3f})\n\t\tSubject: {}\tObject: {}".format(relation, confidence, subj,
                                                                                                  obj))
                    if confidence > conf:
                        if res[(subj, relation, obj)] < confidence:
                            res[(subj, relation, obj)] = confidence
                            print("\t\tAdding to set of extracted relations")
                        else:
                            print("\t\tDuplicate with lower confidence than existing record. Ignoring this.")
                    else:
                        print("\t\tConfidence is lower than threshold confidence. Ignoring this.")
                    print("\t\t==========")

        k += 1
        if k % 5 == 0 and k != 0:
            print("\tProcessed {}/{} sentences".format(k, num_sentences))

    print("Extracted annotations for {} out of total {} sentences".format(len(sentences_extracted), num_sentences))
    print("Relations extracted from this website: {} (Overall: {})".format(len(res), relations_extracted))

    return res


def create_entity_pairs(sents_doc, entities_of_interest, window_size=40):
    '''
    Input: a spaCy Sentence object and a list of entities of interest
    Output: list of extracted entity pairs: (text, entity1, entity2)
    '''
    entities_of_interest = {bert2spacy[b] for b in entities_of_interest}
    ents = sents_doc.ents  # get entities for given sentence

    length_doc = len(sents_doc)
    entity_pairs = []
    for i in range(len(ents)):
        e1 = ents[i]
        if e1.label_ not in entities_of_interest:
            continue

        for j in range(1, len(ents) - i):
            e2 = ents[i + j]
            if e2.label_ not in entities_of_interest:
                continue
            if e1.text.lower() == e2.text.lower():  # make sure e1 != e2
                continue

            if (1 <= (e2.start - e1.end) <= window_size):

                punc_token = False
                start = e1.start - 1 - sents_doc.start
                if start > 0:
                    while not punc_token:
                        punc_token = sents_doc[start].is_punct
                        start -= 1
                        if start < 0:
                            break
                    left_r = start + 2 if start > 0 else 0
                else:
                    left_r = 0

                # Find end of sentence
                punc_token = False
                start = e2.end - sents_doc.start
                if start < length_doc:
                    while not punc_token:
                        punc_token = sents_doc[start].is_punct
                        start += 1
                        if start == length_doc:
                            break
                    right_r = start if start < length_doc else length_doc
                else:
                    right_r = length_doc

                if (right_r - left_r) > window_size:  # sentence should not be longer than window_size
                    continue

                x = [token.text for token in sents_doc[left_r:right_r]]
                gap = sents_doc.start + left_r
                e1_info = (e1.text, spacy2bert[e1.label_], (e1.start - gap, e1.end - gap - 1))
                e2_info = (e2.text, spacy2bert[e2.label_], (e2.start - gap, e2.end - gap - 1))
                if e1.start == e1.end:
                    assert x[e1.start - gap] == e1.text, "{}, {}".format(e1_info, x)
                if e2.start == e2.end:
                    assert x[e2.start - gap] == e2.text, "{}, {}".format(e2_info, x)
                entity_pairs.append((x, e1_info, e2_info))

    return entity_pairs
