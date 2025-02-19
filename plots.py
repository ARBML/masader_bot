import plotext as plt  # type: ignore
from glob import glob
import json
import argparse
from constants import eval_datasets_ids, non_browsing_models, schemata
import numpy as np
from plot_utils import print_table
from utils import get_predictions, evaluate_metadata

args = argparse.ArgumentParser()
args.add_argument("--eval", type=str, default="test")
args.add_argument("--subsets", action="store_true")
args.add_argument("--year", action="store_true")
args.add_argument("--models", type=str, default="all")
args.add_argument("--cost", action="store_true")
args.add_argument("--use_annotations_paper", action="store_true")
args.add_argument("--schema", type = str, default = 'ar')
args.add_argument("--type", type = str, default = "zero_shot")

args = args.parse_args()

# evaluation_subsets = schema[args.schema]['evaluation_subsets']

def plot_by_cost():
    metric_results = {}
    for json_file in json_files:
        results = json.load(open(json_file))
        arxiv_id = json_file.split("/")[-2].replace("_arXiv", "")
        if arxiv_id not in ids:
            continue
        model_name = results["config"]["model_name"]
        if model_name in non_browsing_models:
            continue
        if model_name not in metric_results:
            metric_results[model_name] = []
        metric_results[model_name].append(
            [
                results["cost"]["input_tokens"],
                results["cost"]["output_tokens"],
                results["cost"]["input_tokens"] + results["cost"]["output_tokens"],
                results["cost"]["cost"],
            ]
        )

    final_results = {}
    for model_name in metric_results:
        if len(metric_results[model_name]) == len(ids):
            final_results[model_name] = metric_results[model_name]

    results = []
    for model_name in final_results:
        results.append(
            [model_name] + (np.sum(final_results[model_name], axis=0)).tolist()
        )

    headers = ["MODEL", "INPUT TOKENS", "OUTPUT TOKENS", "TOTAL TOKENS", "COST (USD)"]
    print_table(results, headers)


def plot_by_year():
    metric_results = {}
    for json_file in json_files:
        results = json.load(open(json_file))
        arxiv_id = json_file.split("/")[-2].replace("_arXiv", "")
        if arxiv_id not in ids:
            continue
        model_name = results["config"]["model_name"]
        pred_metadata = results["metadata"]
        if model_name not in metric_results:
            metric_results[model_name] = []
        
        human_json_path = "/".join(json_file.split("/")[:-1]) + "/human-results.json"
        gold_metadata = json.load(open(human_json_path))["metadata"]
        
        if args.use_annotations_paper:
            scores = evaluate_metadata(
                gold_metadata, pred_metadata, use_annotations_paper=True
            )
        else:
            scores = evaluate_metadata(
                gold_metadata, pred_metadata
            )
        metric_results[model_name].append(
            [gold_metadata["Year"], scores["AVERAGE"]]
        )

    final_results = {}
    for model_name in metric_results:
        if len(metric_results[model_name]) == len(ids):
            final_results[model_name] = metric_results[model_name]

    results = []
    for model_name in final_results:
        years = [year for year, _ in metric_results[model_name]]
        scores = [score for _, score in metric_results[model_name]]

        # average score per year
        avg_scores = {}
        for year, score in zip(years, scores):
            if year not in avg_scores:
                avg_scores[year] = []
            avg_scores[year].append(score)

        avg_scores = {
            year: sum(avg_scores[year]) / len(avg_scores[year]) for year in avg_scores
        }
        years = list(avg_scores.keys())
        scores = list(avg_scores.values())

        years, scores = zip(*sorted(zip(years, scores)))
        # plt.scatter(years, scores, label = model_name)
        plt.plot(years, scores, label=model_name)

    plt.title("Average Score per Year")
    plt.xlabel("Year")
    plt.ylabel("Average Score")
    plt.show()

def get_jsons_by_lang():
    json_files_by_language = {}
    for lang in langs:
        for json_file in json_files:
            arxiv_id = json_file.split("/")[-2].replace("_arXiv", "")
            if arxiv_id in eval_datasets_ids[lang][args.eval]:
                if lang not in json_files_by_language:
                    json_files_by_language[lang] = []
                json_files_by_language[lang].append(json_file)
    for lang in langs:
        if lang == 'ar':
            assert len(eval_datasets_ids[lang][args.eval]) == 25
        else:
            assert len(eval_datasets_ids[lang][args.eval]) == 5
    return json_files_by_language

def plot_langs():
    json_files_by_language = get_jsons_by_lang()
    langs = list(json_files_by_language.keys())
    headers = [ "MODEL"] + langs + ["AVERAGE"]
    metric_results = {}
    use_annotations_paper = args.use_annotations_paper
    for lang in langs:
        for json_file in json_files_by_language[lang]:
            results = json.load(open(json_file))        
            model_name = results["config"]["model_name"]
            pred_metadata = results["metadata"]
            if model_name not in metric_results:
                metric_results[model_name] = {}
            human_json_path = "/".join(json_file.split("/")[:-1]) + "/human-results.json"
            gold_metadata = json.load(open(human_json_path))["metadata"]

            scores = evaluate_metadata(
                gold_metadata, pred_metadata,
                schema = lang
            )
            scores = [scores["AVERAGE"]]
            if use_annotations_paper:
                average_ignore_mistakes = evaluate_metadata(
                    gold_metadata, pred_metadata, use_annotations_paper=True
                )["AVERAGE"]
                scores += [average_ignore_mistakes]
                headers += ["AVERAGE^*"]
            if lang not in metric_results[model_name]:
                metric_results[model_name][lang] = []
            metric_results[model_name][lang].append(scores[0])
    final_results = {}
    for model_name in metric_results:
        if "human" in model_name.lower():
            continue
        
        for lang in metric_results[model_name]:
            if len(metric_results[model_name][lang]) == len(eval_datasets_ids[lang][args.eval]):
                if model_name not in final_results:
                    final_results[model_name] = {}
                if lang not in final_results[model_name]:
                    final_results[model_name][lang] = []
                final_results[model_name][lang] = metric_results[model_name][lang]

    results = []
    for model_name in final_results:
        per_model_results = []
        for lang in langs:
            if lang in final_results[model_name]:
                per_model_results.append(100 *sum(final_results[model_name][lang])/len(final_results[model_name][lang]))
            else:
                per_model_results.append(0)
        
        assert len(per_model_results) == len(langs)
        results.append([model_name] +per_model_results+ [np.mean(per_model_results, axis=0).tolist()])
    for r in results:
        assert(len(r)) == len(langs)+2, r
    print_table(results, headers, format = False)
    if use_annotations_paper:
        print(
            "* Computed average by considering metadata exctracted from outside the paper."
        )

def plot_few_shot(lang = 'ar'):
    headers = [ "MODEL"] + [f'{idx}-fewshot' for idx in [0, 1, 3, 5]]
    metric_results = {}
    use_annotations_paper = args.use_annotations_paper
    for json_file in json_files:
        results = json.load(open(json_file))
        arxiv_id = json_file.split("/")[2].replace("_arXiv", "").replace('.pdf', '')
        if arxiv_id not in eval_datasets_ids[lang][args.eval]:
            continue
        model_name = results["config"]["model_name"]
        pred_metadata = results["metadata"]
        if model_name not in metric_results:
            metric_results[model_name] = {}
        human_json_path = "/".join(json_file.split("/")[:-1]) + "/human-results.json"
        human_json_path = human_json_path.replace(f"/zero_shot", "")
        gold_metadata = json.load(open(human_json_path))["metadata"]
        for i in [0, 1, 3, 5]:
            try:
                if i > 0:
                    pred_metadata = json.load(open(json_file.replace('zero_shot', f'few_shot/{i}')))['metadata']
            except:
                break

            if i not in metric_results[model_name]:
                metric_results[model_name][i] = []

            scores = evaluate_metadata(
                gold_metadata, pred_metadata,
                schema = args.schema
            )
            scores = [scores["AVERAGE"]]
            if use_annotations_paper:
                average_ignore_mistakes = evaluate_metadata(
                    gold_metadata, pred_metadata, use_annotations_paper=True
                )["AVERAGE"]
                scores = [average_ignore_mistakes]
            metric_results[model_name][i].append(scores[0])
    results = []
    for model_name in metric_results:
        if "human" in model_name.lower():
            continue
        few_shot_scores = []
        for i in [0, 1, 3, 5]:
            try:
                if len(metric_results[model_name][i]) == len(eval_datasets_ids[lang][args.eval]):
                    few_shot_scores.append(float(np.mean(metric_results[model_name][i]) * 100))
                else:
                    few_shot_scores.append(0)
            except:
                few_shot_scores.append(0)
        results.append([model_name] + few_shot_scores)
    print_table(results, headers, format = False)
    if use_annotations_paper:
        print(
            "* Computed average by considering metadata exctracted from outside the paper."
        )

def plot_table(lang = 'ar'):
    evaluation_subsets = schemata[lang]['evaluation_subsets']
    headers = [ "MODEL"] + [c for c in evaluation_subsets] + ["AVERAGE"]
    metric_results = {}
    use_annotations_paper = args.use_annotations_paper
    for json_file in json_files:
        results = json.load(open(json_file))
        arxiv_id = json_file.split("/")[2].replace("_arXiv", "").replace('.pdf', '')
        if arxiv_id not in eval_datasets_ids[lang][args.eval]:
            continue
        model_name = results["config"]["model_name"]
        pred_metadata = results["metadata"]
        if model_name not in metric_results:
            metric_results[model_name] = []
        human_json_path = "/".join(json_file.split("/")[:-1]) + "/human-results.json"
        human_json_path = human_json_path.replace(f"/{args.type}", "")
        gold_metadata = json.load(open(human_json_path))["metadata"]
        scores = {c: 0 for c in evaluation_subsets}

        scores = evaluate_metadata(
            gold_metadata, pred_metadata,
            schema = args.schema
        )
        scores = [scores[c] for c in evaluation_subsets] + [scores["AVERAGE"]]
        if use_annotations_paper:
            average_ignore_mistakes = evaluate_metadata(
                gold_metadata, pred_metadata, use_annotations_paper=True
            )["AVERAGE"]
            scores += [average_ignore_mistakes]
            headers += ["AVERAGE^*"]
        metric_results[model_name].append(scores)
    final_results = {}
    for model_name in metric_results:
        if "human" in model_name.lower():
            continue
        if len(metric_results[model_name]) == len(eval_datasets_ids[lang][args.eval]):
            final_results[model_name] = metric_results[model_name]

    results = []
    for model_name in final_results:
        results.append(
            [model_name] + (np.mean(final_results[model_name], axis=0) * 100).tolist()
        )

    print_table(results, headers, format = True)
    if use_annotations_paper:
        print(
            "* Computed average by considering metadata exctracted from outside the paper."
        )


def process_subsets(metric_results, subset, use_annotations_paper, lang = 'ar'):
    evaluation_subsets = schemata[lang]['evaluation_subsets']
    headers = evaluation_subsets[subset]

    results_per_model = {}
    results_per_model_with_annotations = {}
    results = []
    for model_name in metric_results:
        predictions, predictions_with_annotations = metric_results[model_name]
        if len(predictions) != len(ids):
            continue
        for prediction, prediction_with_annotations in zip(predictions, predictions_with_annotations):
            if model_name not in results_per_model:
                results_per_model[model_name] = []
            if model_name not in results_per_model_with_annotations:
                results_per_model_with_annotations[model_name] = []
            results_per_model[model_name].append(
                [prediction[column] for column in headers]
            )
            if use_annotations_paper:
                results_per_model_with_annotations[model_name].append(
                    [prediction_with_annotations[column] for column in headers]
                )
        scores = np.mean(results_per_model[model_name], axis=0).tolist()
        if use_annotations_paper:
            scores_with_annotations = np.mean(results_per_model_with_annotations[model_name], axis=0).tolist()
            row = [model_name] + scores + [np.mean(scores)] + [np.mean(scores_with_annotations)]
        else:
            row = [model_name] + scores + [np.mean(scores)]
        results.append(row)
    return results


def plot_subsets(lang = 'ar'):
    evaluation_subsets = schemata[lang]['evaluation_subsets']
    metric_results = {}
    for json_file in json_files:
        results = json.load(open(json_file))
        arxiv_id = json_file.split("/")[-2].replace("_arXiv", "")
        if arxiv_id not in ids or "human" in json_file:
            continue
        model_name = results["config"]["model_name"]
        if model_name not in metric_results:
            metric_results[model_name] = [[], []]
        human_json_path = "/".join(json_file.split("/")[:-1]) + "/human-results.json"
        gold_metadata = json.load(open(human_json_path))["metadata"]
        pred_metadata = results["metadata"]
        scores = get_predictions(
            gold_metadata, pred_metadata
        )
        if args.use_annotations_paper:
            scores_with_annotations = get_predictions(
                gold_metadata, pred_metadata, use_annotations_paper=True
            )
            metric_results[model_name][0].append(scores)
            metric_results[model_name][1].append(scores_with_annotations)
        else:
            metric_results[model_name][0].append(scores)
            metric_results[model_name][1].append([])

    for subset in evaluation_subsets:
        headers = evaluation_subsets[subset]
        headers = (
            ["MODEL"] + [h.capitalize() for h in headers] + ["AVERAGE"]
        )
        if args.use_annotations_paper:
            headers += ["AVERAGE^*"]  # capitalize each letter in header name
        results = process_subsets(metric_results, subset, args.use_annotations_paper)
        print_table(results, headers, title=f"Graph for {subset}")


if __name__ == "__main__":
    json_files = glob(f"static/results/**/{args.type}/*.json")
    ids = []
    if args.schema == 'all':
        langs = ['ar', 'en', 'jp', 'fr', 'ru']
    else:
        langs = [args.schema]
            
    # if args.models != "all":
    #     json_files = [
    #         file
    #         for file in json_files
    #         if any(model.lower() in file.lower() for model in args.models.split(","))
    #     ]

    if args.type == 'few_shot':
        json_files = glob(f"static/results/**/zero_shot/*.json")
        plot_few_shot()
    elif args.year:
        plot_by_year()
    elif args.cost:
        plot_by_cost()
    elif args.schema == 'all':
        plot_langs()
    else:
        if args.subsets:
            plot_subsets()
        else:
            plot_table(lang = args.schema)
