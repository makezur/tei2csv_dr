import csv
import itertools
import numpy as np

from bs4 import BeautifulSoup

from os import walk


def print_if(data, verbose=False):
    if verbose:
        print(data)


def inverse_dict(list_to_inverse):
    result_dict = dict()

    for index in range(len(list_to_inverse)):
        result_dict[list_to_inverse[index]] = index

    return result_dict

# dictionary for TEI names and real names correspondence


def get_persons_dict(parser, prefix="#"):
    persons = dict()

    xml_persons = parser.find_all("person")
    if len(xml_persons) == 0:
        raise Exception("Parse error")

    for person_tag in parser.find_all("person"):
        xml_id = "xml:id"

        if xml_id in person_tag.attrs:
            person_id = prefix + person_tag[xml_id]
        else:
            raise Exception("Parse error")

        if person_tag.find("persname"):
            person_name = person_tag.find("persname").string.strip()
        else:
            raise Exception("Parse error")

        persons[person_id] = person_name

    return persons


def get_speaker_data(speaker_tag):
    if "who" in speaker_tag.attrs:
        if speaker_tag.contents is None:
            print(speaker_tag)
            raise Exception("Parse error", "len error")

        stop_list_names = {"speaker", "stage"}

        speech_text = str()
        for child_tag in speaker_tag.contents:
            if child_tag.name not in stop_list_names:
                if child_tag.name == "p":
                    speech_text += " " + child_tag.string.strip()
                else:
                    if len(str(child_tag).strip()) == 0:
                        continue

                    print("check me: adding non flat speech")
                    print(child_tag)
                    speech_text += " " + str(child_tag)

        return speaker_tag["who"], speech_text
    else:
        print(speaker_tag)
        print(speaker_tag.parent)
        raise Exception("Parse error", "sp tag doesn't have who attr")


def div_by_acts_and_scenes(parser, verbose):
    tag_act_list = ["div", "stage", "sp"]
    action_list = parser.find_all(tag_act_list)

    acts = list()

    current_act = list()
    current_scene = list()

    act_num = 0

    # loop to collect speeches and other staff from parser

    for action_tag in action_list:
        if action_tag.name == "div":
            if "type" in action_tag.attrs:
                type_value = action_tag["type"]

                if type_value == "act":
                    # next act
                    if len(current_act) != 0:
                        print_if("append act", verbose)

                        acts.append(current_act)
                        current_act = list()

                    act_num += 1
                    print_if(["акт", act_num], verbose)
                elif type_value == "scene":
                    # next scene
                    if len(current_scene) != 0:
                        print_if("append scene", verbose)

                        current_act.append(current_scene)
                        current_scene = list()

                    print_if("сцена", verbose)
                else:
                    raise Exception("Parse error", "bad div type")
            else:
                raise Exception("Parse error", "no div type")

        if action_tag.name == "sp":
            current_scene.append(get_speaker_data(action_tag))

        if action_tag.name == "stage":
            print_if("stage todo", verbose)
            print_if(action_tag)

    # add final scene and act
    print_if("append scene", verbose)
    print_if("append act", verbose)

    current_act.append(current_scene)
    acts.append(current_act)

    return acts


def make_score_table(list_for_table):
    return np.zeros((len(list_for_table), len(list_for_table)))


def compute_stats(acts):
    acts_stat = list()

    current_act_stat = list()
    current_scene_stat = dict()

    # stats names
    sp_size = "speech sizes"
    sp_mean = "speech mean size"
    sp_std = "speech std"
    sp_max = "speech max size"
    sp_amount = "speeches amount"

    __scene = "__scene"
    __act = "__act"

    for act in acts:
        for scene in act:
            # stats for whole scene
            current_scene_stat[__scene] = dict()
            current_scene_stat[__scene][sp_size] = list()

            for speech in scene:
                speaker = speech[0]
                speech_text = speech[1]

                # init
                if speaker not in current_scene_stat:
                    current_scene_stat[speaker] = dict()
                    current_scene_stat[speaker][sp_size] = list()

                current_scene_stat[speaker][sp_size].append(len(speech_text))
                current_scene_stat[__scene][sp_size].append(len(speech_text))

            # compute stats using numpy
            for speaker in current_scene_stat.keys():
                arr_for_stats = np.array(current_scene_stat[speaker][sp_size])

                current_scene_stat[speaker][sp_mean] = np.mean(arr_for_stats)
                current_scene_stat[speaker][sp_std] = np.std(arr_for_stats)
                current_scene_stat[speaker][sp_max] = np.max(arr_for_stats)
                current_scene_stat[speaker][sp_amount]= arr_for_stats.size

            # for the whole scene
            arr_for_stats = np.array(current_scene_stat[__scene][sp_size])

            current_scene_stat[__scene][sp_mean] = np.mean(arr_for_stats)
            current_scene_stat[__scene][sp_std] = np.std(arr_for_stats)
            current_scene_stat[__scene][sp_max] = np.max(arr_for_stats)
            current_scene_stat[__scene][sp_amount] = arr_for_stats.size

            # push results for scene
            current_act_stat.append(current_scene_stat)
            current_scene_stat = dict()

        # push results for act
        acts_stat.append(current_act_stat)
        current_act_stat = list()

    return acts_stat

# make_score function computes the weights of relations in our graph based on the generated stats
# the current formula is just the pairwise sum of speeches amount in each scene
# but our plain, i guess, is to try different scoring methods


def make_score(score_table, acts, stats, persons_list, persons_dict, persons_inverse_dict):
    # this is where the magic happens
    for act_stats in stats:
        for scene_stats in act_stats:
            list_of_interest = list()
            for person_name in scene_stats.keys():
                # mm
                if person_name not in persons_inverse_dict:
                    continue

                person_id = persons_inverse_dict[person_name]
                person_speeches = scene_stats[person_name]["speeches amount"]

                list_of_interest.append((person_id, person_speeches))

            for first, second in itertools.combinations(list_of_interest, 2):
                score_table[first[0]][second[0]] += first[1] + second[1]


def table_to_csv(cvs_name, table, persons_list, persons_dict):
    header = ["Source", "Type" , "Target", "Weight"]

    type_string = "Undirected"
    csv_file = open(cvs_name, "w")

    # мб тут параметры родить какие
    csv_writer = csv.writer(csv_file)

    csv_writer.writerow(header)

    for first_index in range(len(persons_list)):
        for second_index in range(first_index):
            source = persons_dict[persons_list[first_index]]
            target = persons_dict[persons_list[second_index]]

            # maybe divide by two....
            weight = table[first_index][second_index] + table[second_index][first_index]
            # weight /= 2

            list_to_write = [source, type_string, target, weight]
            csv_writer.writerow(list_to_write)

    csv_file.close()


def tei_to_csv(input_filename, output_filename, verbose=False):
    read_file = open(input_filename, "r")
    text = read_file.read()
    soup = BeautifulSoup(text, "lxml")

    persons_dict = get_persons_dict(soup)
    persons_list = list(persons_dict.keys())
    persons_inverse_dict = inverse_dict(persons_list)

    print_if(persons_dict, verbose)
    acts = div_by_acts_and_scenes(soup, verbose)

    score_table = make_score_table(persons_list)
    stats = compute_stats(acts)
    make_score(score_table, acts, stats, persons_list, persons_dict, persons_inverse_dict)

    table_to_csv(output_filename, score_table, persons_list, persons_dict)


def parse_tei_folder(input_folder, output_folder, verbose=False):
    for path, dirs, filenames in walk(input_folder):
        for filename in filenames:
            if filename.endswith(".xml"):
                new_filename = filename[:-4] + ".csv"

                print_if(["converting: ", path + "/" + filename, output_folder + "/" + new_filename], verbose)
                tei_to_csv(path + "/" + filename, output_folder + "/" + new_filename, verbose)

if __name__ == "__main__":
    parse_tei_folder("./xml_folder", "./csv_folder", verbose=False)
