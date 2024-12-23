import anthropic
from glob import glob
import os
import re
import arxiv
from search_arxiv import ArxivSearcher, ArxivSourceDownloader
import json
import pdfplumber
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from utils import *
import argparse
import google.generativeai as genai # type: ignore
import streamlit as st
from constants import *

logger = setup_logger()
        
load_dotenv()


client = anthropic.Anthropic(api_key=os.environ['anthropic_key'])
chatgpt_client = OpenAI(api_key=os.environ['chatgpt_key'])
genai.configure(api_key=os.environ['gemini_key'])
# print([m.name for m in genai.list_models()])
# raise()

stop_event = threading.Event()  # Event to signal the spinner to stop
spinner_thread = threading.Thread(target=spinner_animation, args=(stop_event,))

columns = ['Name', 'Subsets', 'Link', 'HF Link', 'License', 'Year', 'Language', 'Dialect', 'Domain', 'Form', 'Collection Style', 'Description', 'Volume', 'Unit', 'Ethical Risks', 'Provider', 'Derived From', 'Paper Title', 'Paper Link', 'Script', 'Tokenized', 'Host', 'Access', 'Cost', 'Test Split', 'Tasks',  'Venue Title', 'Citations', 'Venue Type', 'Venue Name', 'Authors', 'Affiliations', 'Abstract']
extra_columns = ['Subsets', 'Year', 'Description', 'Paper Link', 'Venue Title', 'Citations', 'Venue Type', 'Venue Name', 'Authors', 'Affiliations', 'Abstract','Year']

publication_columns = ['Paper Title', 'Paper Link', 'Year', 'Venue Title', 'Venue Type', 'Venue Name']
content_columns = ['Volume', 'Unit', 'Tokenized', 'Script', 'Form', 'Collection Style', 'Domain', 'Ethical Risks']
accessability_columns = ['Provider', 'Host', 'Link', 'License', 'Cost']
diversity_columns = ['Language', 'Subsets', 'Dialect']
evaluation_columns = ['Test Split', 'Tasks', 'Derived From']
validation_columns = content_columns+accessability_columns+diversity_columns+evaluation_columns

sheet_id = "1YO-Vl4DO-lnp8sQpFlcX1cDtzxFoVkCmU1PVw_ZHJDg"
sheet_name = "filtered_clean"
url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

import pandas as pd
df = pd.read_csv(url, usecols=range(34))
df.columns.values[0] = "No."
df.columns.values[1] = "Name"
print(column_options['Dialect'])
questions = f"1. What is the name of the dataset? Only use a short name of the dataset. \n\
  2. What are the subsets of this dataset? \n\
  3. What is the link to access the dataset? The link most contain the dataset. \n\
  4. What is the Huggingface link of the dataset? \n\
  5. What is the License of the dataset? Options: {column_options['License']} \n\
  6. What year was the dataset published? \n\
  7. Is the dataset multilingual or ar? \n\
  8. Choose a dialect for the dataset from the following options: {column_options['Dialect']}. If the type of the dialect is not clear output mixed. \n\
  9. What is the domain of the dataset? Options: {column_options['Domain']} \n\
  10. What is the form of the dataset? Options {column_options['Form']} \n\
  11. How was this dataset collected? Options: {column_options['Collection Style']} \n\
  12. Write a brief description of the dataset. \n\
  13. What is the size of the dataset? Output numbers only with , seperated each thousand\n\
  14. What is the unit of the size? Options: {column_options['Unit']}. Only use documents for datasets that contain documents or files as examples. \n\
  15. What is the level of the ethical risks of the dataset? Options: {column_options['Ethical Risks']}\n\
  16. What entity is the provider of the dataset? \n\
  17. What dataset is this dataset derived from? \n\
  18. What is the paper title? \n\
  19. What is the paper link? \n\
  20. What is the script of this dataset? Options: {column_options['Script']} \n\
  21. Is the dataset tokenized? Options: {column_options['Tokenized']} \n\
  22. Who is the host of the dataset? Options: {column_options['Host']} \n\
  23. What is the accessability of the dataset? Options: {column_options['Access']} \n\
  24. What is the cost of the dataset? If the dataset is free don't output anything. \n\
  25. Does the dataset contain a test split? Options: {column_options['Test Split']} \n\
  26. What is the task of the dataset. If there are multiple tasks, separate them by ','. Options: {column_options['Tasks']} \n\
  27. What is the Venue title this paper was published in? \n\
  28. How many citations this paper got? \n\
  29. What is the venue the dataset is published in? Options: {column_options['Venue Type']} \n\
  30. What is the Venue full name this paper was published in? \n\
  31. Who are the authors of the paper, list them separated by comma. \n\
  32. What are the affiliations of the authors, separate by comma. \n\
  33. What is the abstract of the dataset?"

def compute_filling(metadata):
    return len([m for m in metadata if m!= '']) / len(metadata)

def compute_cost(message):
  try:
    num_inp_tokens = message.usage.input_tokens
    num_out_tokens = message.usage.output_tokens
    cost =(num_inp_tokens / 1e6) * 3 + (num_out_tokens / 1e6) * 15 
  except:
    num_inp_tokens = -1
    num_out_tokens = -1
    cost = -1
      
  return {
        'cost': cost,
        'input_tokens': num_inp_tokens,
        'output_tokens': num_out_tokens
    }
      

@spinner_decorator
def is_resource(abstract):
  prompt = f" You are given the following abstract: {abstract}, does the abstract indicate there is a published Arabic dataset or multilingual dataset that contains Arabic? please answer 'yes' or 'no' only"  
  model = genai.GenerativeModel("gemini-1.5-flash",system_instruction ="You are a prefoessional research paper reader" )  
  
  message = model.generate_content(prompt, 
        generation_config = genai.GenerationConfig(
        max_output_tokens=1000,
        temperature=0.0,
    ))
  
  return True if 'yes' in message.text.lower() else False

def fix_options(metadata):
    fixed_metadata = {}
    for column in metadata:
        if column in column_options:
            options = [c.strip() for c in column_options[column].split(',')]
            pred_option = metadata[column]
            if pred_option in options:
                fixed_metadata[column] = pred_option
            elif pred_option == '':
                fixed_metadata[column] = ''
            else:                    
                fixed_metadata[column] = find_best_match(pred_option, options)
        else:
            fixed_metadata[column] = metadata[column]


    return fixed_metadata

import re

def process_url(url):
    url = re.sub(r'\\url\{(.*?)\}', r'\1', url).strip()
    url = re.sub('huggingface', 'hf', url)
    return url

def postprocess(metadata):
    metadata['Link'] = process_url(metadata['Link'])
    metadata['HF Link'] = process_url(metadata['HF Link'])

    return metadata

def match_titles(title, masader_title):
    if isinstance(masader_title, float):
        return 0
    return difflib.SequenceMatcher(None, title, masader_title).ratio()

@spinner_decorator
def validate(metadata):
    results = {
        # 'PUBLICATION': 0,
        'CONTENT':0,
        'ACCESSABILITY':0,
        'DIVERSITY':0,
        'EVALUATION':0,
        'AVERAGE':0,
    }

    dataset = df[df['Paper Title'].apply(lambda x: match_titles(str(metadata['Paper Title']), x)) > 0.8]

    if len(dataset) <= 0:
        return results

    for column in validation_columns:
        gold_answer = np.asarray((dataset[column]))[0]
        if str(gold_answer) == 'nan':
            gold_answer = ''
        pred_answer = metadata[column]
        if pred_answer.lower() == str(gold_answer).lower():
            results['AVERAGE'] += 1/len(validation_columns)
            if column in publication_columns:
                results['PUBLICATION'] += 1/6
            elif column in content_columns:
                results['CONTENT'] += 1/8
            elif column in accessability_columns:
                results['ACCESSABILITY']+= 1/5
            elif column in diversity_columns:
                results['DIVERSITY']+= 1/3
            elif column in evaluation_columns:
                results['EVALUATION'] += 1/3
    return results

def get_answer(answers, question_number = '1.'):
    for answer in answers:
        if answer.startswith(question_number):
            return re.sub(r'(\d+)\.', '', answer).strip()

@spinner_decorator
def get_metadata(paper_text, model_name):
  prompt = f"You are given a dataset paper {paper_text}, you are requested to answer the following questions about the dataset {questions}"
  message = client.messages.create(
      model=model_name,
      max_tokens=1000,
      temperature=0,
      system="You are a profressional research paper reader. You will be provided 33 questions. \
      If a question has choices which are separated by ',' , only provide an answer from the choices. \
      If the question has no choices and the answer is not found in the paper, then answer only N/A.",
      messages=[
          {
              "role": "user",
              "content": [
                  {
                      "type": "text",
                      "text": prompt
                  }
              ]
          }
      ]
  )
  predictions = {}
  response = message.content[0].text

  for i in range(1, 34):
      predictions[columns[i-1]] = get_answer(response.split('\n'), question_number=f'{i}.')
  return message, predictions

@spinner_decorator
def get_metadata_gemini(paper_text, model_name):
  prompt = f"You are given a dataset paper {paper_text}, you are requested to answer the following questions about the dataset {questions}"
  
  model = genai.GenerativeModel(model_name,system_instruction ="You are a profressional research paper reader. You will be provided 33 questions. \
      If a question has choices which are separated by ',' , only provide an answer from the choices. \
      If the question has no choices and the answer is not found in the paper, then answer only N/A." )  
  
  message = model.generate_content(prompt, 
        generation_config = genai.GenerationConfig(
        max_output_tokens=1000,
        temperature=0.0,
    ))
  predictions = {}
  response = message.text
  for i in range(1, 34):
      predictions[columns[i-1]] = get_answer(response.split('\n'), question_number=f'{i}.')
  return message, predictions

def get_metadata_chatgpt(paper_text, model_name):
    prompt = f"You are given a dataset paper {paper_text}, you are requested to answer the following questions about the dataset. \
    {questions}\
    For each question, output a short and concise answer responding to the exact question without any extra text. If the answer is not provided, then answer only N/A.\
    "
    message = chatgpt_client.chat.completions.create(
            model= model_name,
            messages=[{"role": "system", "content": "You are a profressional research paper reader"},
                {"role": "user", "content":prompt}]
            )
    response = message.choices[0].message.content
    predictions = {}

    for i in range(1, 34):
      predictions[columns[i-1]] = get_answer(response.split('\n'), question_number=f'{i}.')
    
    return message, predictions

@spinner_decorator
def clean_latex(path):
    os.system(f'arxiv_latex_cleaner {path}')

@spinner_decorator
def get_search_results(keywords, month, year):
    searcher = ArxivSearcher(max_results=10)
    return searcher.search(
        keywords= keywords,
        categories=['cs.AI', 'cs.LG', 'cs.CL'],
        month=month,
        year=year,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    
def run(args):
    # Example search for machine learning papers from March 2024
    submitted = None
    if args:
        year = args.year
        month = args.month
        keywords = args.keywords.split(' ')
        verbose = args.verbose
        check_abstract = args.check_abstract
        model_name = args.model_name
        overwrite = args.overwrite
    else:
        verbose = True
        with st.form(key='search_form'):
            check_abstract = st.checkbox("Abstract")
            overwrite = st.checkbox("Overwrite")

            # Create columns for arranging elements in a single row
            col1, col2, col3, col4, col5 = st.columns(5)

            with col1:
                keywords = st.text_input("Keywords/Title")
            with col2:
                year = st.number_input("Year", min_value=1900, max_value=2100, value=2024, step=1)
            with col3:
                month = st.number_input("Month", min_value=1, max_value=12, value=1, step=1)
            with col4:
                model_name = st.selectbox("Model", ["gemini-1.5-flash", "claude-3-5-sonnet-latest", "gpt-4o"], index=0)
            with col5:
                submitted = st.form_submit_button("Search")

    # Process input values
    keywords = keywords.split(',')

    if submitted or args:
        with st.spinner('🔍 Searching arXiv ...'):
            if verbose:
                logger.info('🔍 Searching arXiv ...')
            search_results = get_search_results(keywords, month, year)

        for r in search_results:
            abstract = r['summary']
            article_url = r['article_url']
            title = r['title']
            year = r['published'].split('-')[0]

            paper_id = article_url.split('/')[-1]
            paper_id_no_version = paper_id.replace('v1', '').replace('v2', '').replace('v3', '')
                

            if verbose:
                logger.info(f'🎧 Reading {title} ...')
            
            re_check = not os.path.isdir(f'static/results/{paper_id_no_version}')
            _is_resource = True
            if check_abstract:
                if re_check:
                    with st.spinner('🚧 Checking Abstract ...'):
                        if verbose:
                            logger.info('🚧 Checking Abstract ...')
                        _is_resource = is_resource(abstract)

            if _is_resource:
                if re_check:
                    downloader = ArxivSourceDownloader(download_path="static/results")
        
                    # Download and extract source files
                    success, path = downloader.download_paper(paper_id, verbose=verbose)
                    with st.spinner('✨ Cleaning Latex ...'):
                        if verbose:
                            logger.info('✨ Cleaning Latex ...')
                        clean_latex(path)
                else:
                    success = True
                    path = f'static/results/{paper_id_no_version}'

                if not success:
                    continue
                
                if len(glob(f'{path}/*.tex')) > 0:
                    path = f'{path}_arXiv'

                save_path = f'{path}/{model_name}-results.json'

                if os.path.exists(save_path) and not overwrite:
                    with st.spinner('📂 Loading saved results ...'):
                        logger.info('📂 Loading saved results ...')
                        results = json.load(open(save_path))
                        st.write(results)
                        st.link_button("Open using Masader Form", f"https://masaderform-production.up.railway.app/?json_url=https://masaderbot-production.up.railway.app/app/{save_path}")
                        return results
                source_files = glob(f'{path}/*.tex')+glob(f'{path}/*.pdf')
                
                if len(source_files):
                    source_file = source_files[0]
                    with st.spinner(f'📖 Reading {source_file} ...'):
                        if verbose:
                            logger.info(f'📖 Reading {source_file} ...')
                        if source_file.endswith('.pdf'):
                            with pdfplumber.open(source_file) as pdf:
                                text_pages = []
                                for page in pdf.pages:
                                    text_pages.append(page.extract_text())
                                paper_text = ' '.join(text_pages)
                        elif source_file.endswith('.tex'):
                            paper_text = open(source_file, 'r').read() # maybe clean comments
                        else:
                            if verbose:
                                logger.error('Not acceptable source file')
                            continue
                    with st.spinner('🧠 Extracting Metadata ...'):
                        if verbose:
                            logger.info(f'🧠 {model_name} is extracting Metadata ...')
                        if 'claude' in model_name.lower(): 
                            message, metadata = get_metadata(paper_text, model_name)
                        elif 'gpt' in model_name.lower():
                            message , metadata = get_metadata_chatgpt(paper_text, model_name)
                        elif 'gem' in model_name.lower():
                            message, metadata = get_metadata_gemini(paper_text, model_name)
                    cost = compute_cost(message)

                    metadata = {k:str(v) for k,v in metadata.items()}

                    if 'N/A' in metadata['Venue Title']:
                        metadata['Venue Title'] = 'arXiv'
                    if 'N/A' in metadata['Venue Type']:
                        metadata['Venue Title'] = 'Preprint'
                    if 'N/A' in metadata['Paper Link']:
                        metadata['Paper Link'] = article_url
                    
                    metadata['Year'] = str(year)
                    
                    for c in metadata:
                        if 'N/A' in metadata[c]:
                            metadata[c] = ''
                        if metadata[c] is None:
                            metadata[c] = ''

                    metadata = fix_options(metadata)
                    metadata = postprocess(metadata)

                    validation_results = validate(metadata)
                    results = {}
                    results ['metadata'] = metadata
                    results ['cost'] = cost
                    results ['validation'] = validation_results
                    results ['config'] = {
                        'model_name': model_name,
                        'month': month,
                        'year': year,
                        'keywords': keywords
                    }
                    results['ratio_filling'] = compute_filling(metadata)
                    if verbose:
                        logger.info(f"📊 Validation socre: {validation_results['AVERAGE']*100:.2f} %")

                    with st.spinner('📥 Saving Results ...'):
                        # remove the subsets
                        results['metadata']['Subsets'] = []
                        with open(save_path, "w") as outfile:
                            logger.info(f"📥 Results saved to: {save_path}") 
                            json.dump(results, outfile, indent=4)
                    st.write(results)
                    st.link_button("Open using Masader Form", f"https://masaderform-production.up.railway.app/?json_url=https://masaderbot-production.up.railway.app/app/{save_path}")
                    return results

            else:
                logger.info('Abstract indicates resource: False')
                st.error('Abstract indicates resource: False')
        else:
            st.error('No papers found')

def create_args():
    parser = argparse.ArgumentParser(description='Process keywords, month, and year parameters')
    
    # Add arguments
    parser.add_argument('-k', '--keywords', 
                        type=str, 
                        required=False,
                        help='space separated keywords')
    
    parser.add_argument('-t', '--title', 
                        type=str, 
                        required=False,
                        help='title of the paper')
    
    parser.add_argument('-m', '--month', 
                        type=int, 
                        required= False,
                        default = None,
                        help='Month (1-12)')
    
    parser.add_argument('-y', '--year', 
                        type=int, 
                        required= False,
                        default = None,
                        help='Year (4-digit format)')

    parser.add_argument('-n', '--models', 
                        type=str, 
                        required=False,
                        default = 'claude-3-5-sonnet-latest',
                        help='Name of the model to use')
    
    parser.add_argument('-c', '--check_abstract', 
                        action = 'store_true',
                        help='whether to check the abstract')
    
    parser.add_argument('-v', '--verbose', 
                        action="store_true",
                        help='whether to check the abstract')
    
    parser.add_argument('-o', '--overwrite', 
                        action="store_true",
                        help='overwrite the extracted metadata')
    
    parser.add_argument('-mv', '--masader_validate', 
                        action="store_true",
                        help='validate on masader dataset')
    
    parser.add_argument('-mt', '--masader_test', 
                        action="store_true",
                        help='test on masader dataset')
    
    parser.add_argument('-agg', '--aggergate', 
                        action="store_true",
                        help='aggergate and show all metrics')

    # Parse arguments
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    # args = create_args()
    args = None
    run(args)