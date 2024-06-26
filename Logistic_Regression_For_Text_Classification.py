# -*- coding: utf-8 -*-
import re
import numpy as np

def build_dict(url):
  corpus = sc.textFile (url)
  validLines = corpus.filter(lambda x : 'id' in x)
  keyAndText = validLines.map(lambda x : (x[x.index('id="') + 4 : x.index('" url=')], x[x.index('">') + 2:]))

  regex = re.compile('[^a-zA-Z]')
  keyAndListOfWords = keyAndText.map(lambda x : (str(x[0]), regex.sub(' ', x[1]).lower().split()))
  allWords = keyAndListOfWords.flatMap(lambda x: ((j, 1) for j in x[1]))
  allCounts = allWords.reduceByKey (lambda a, b: a + b)
  topWords = allCounts.takeOrdered (20000, lambda x : (-x[1], x[0]))
  twentyK = sc.parallelize(range(20000))
  dictionary = twentyK.map (lambda x : (topWords[x][0], x))
  return dictionary.cache()

dictionary = build_dict("s3://chrisjermainebucket/comp330_A5/TrainingDataOneLinePerDoc.txt")
dictionary.lookup("applicant")[0]
dictionary.lookup("and")[0]
dictionary.lookup("attack")[0]
dictionary.lookup("protein")[0]
dictionary.lookup("car")[0]

"""# Task2"""

def convert(lst):
  arr = np.zeros(20000)
  for idx in lst:
    arr[idx] += 1
  return arr

def toBinary(arr):
  for i in range(20000):
    if arr[i] >= 1:
      arr[i] = 1
  return arr

corpus = sc.textFile ("s3://chrisjermainebucket/comp330_A5/TrainingDataOneLinePerDoc.txt")
validLines = corpus.filter(lambda x : 'id' in x)
keyAndText = validLines.map(lambda x : (x[x.index('id="') + 4 : x.index('" url=')], x[x.index('">') + 2:]))

regex = re.compile('[^a-zA-Z]')
keyAndListOfWords = keyAndText.map(lambda x : (str(x[0]), regex.sub(' ', x[1]).lower().split()))
allWords = keyAndListOfWords.flatMap(lambda x: ((j, 1) for j in x[1]))
allCounts = allWords.reduceByKey (lambda a, b: a + b)
topWords = allCounts.takeOrdered (20000, lambda x : (-x[1], x[0]))
twentyK = sc.parallelize(range(20000))
dictionary = twentyK.map (lambda x : (topWords[x][0], x))

word_doc = keyAndListOfWords.flatMap(lambda x: ((j, str(x[0])) for j in x[1]))
word_idx_doc = dictionary.join(word_doc)
doc_idx = word_idx_doc.map(lambda x : (x[1][1], x[1][0]))
doc_wordcnt = doc_idx.groupByKey().map(lambda x : (x[0], list(x[1]))).map(lambda x : (x[0], convert(x[1])))
doc_tf = doc_wordcnt.map(lambda x : (x[0], x[1] / np.sum(x[1])))
num_docs = keyAndListOfWords.count()
binary_wordcnt = doc_wordcnt.map(lambda x : (-1, toBinary(x[1])))
aggregated = binary_wordcnt.aggregateByKey(np.zeros(20000), lambda a, b: a + b, lambda a, b: a + b)
occur = aggregated.first()[1]
idf = np.log(num_docs / occur)
tf_idf = doc_tf.map(lambda x : (x[0], np.multiply(x[1], idf)))
# tf_idf = tf_idf.map(lambda x : (x[0], np.append(x[1], [1])))
# Compute mean and std
mean = tf_idf.values().sum() / tf_idf.count()
std = np.sqrt(tf_idf.map(lambda x : np.square(x[1] - mean)).reduce(lambda a, b: a + b) / float(tf_idf.count()))
tf_idf = tf_idf.map(lambda x : (x[0], np.nan_to_num((x[1] - mean) / (1000 * std)))).cache() # avoid potential divide by 0

def negative_llh(x, r, penal_param):
  theta = r.dot(x[1])
  if "AU" in str(x[0]):
    yi = 1
  else:
    yi = 0
  return -yi*theta + np.log(1 + np.exp(theta)) + penal_param * r.dot(r)

def compute_grad(x, r, penal_param):
  theta = r.dot(x[1])
  if "AU" in str(x[0]):
    yi = 1
  else:
    yi = 0
  exp_theta = np.exp(theta)
  temp = -yi * x[1] + x[1] * (exp_theta / (1 + exp_theta))
  return temp + 2 * penal_param * r

def gd(r_init, penal_param, tf_idf):
  rate = 0.1
  r = r_init
  diff = 1 # Initialize difference to be 1
  total = tf_idf.count()
  # dividing the LLH (and thus also the gradient) by the total number of documents to avoid Nah issue (Also useful for improving f1 and speed up)
  prev_llh = (tf_idf.map(lambda x : negative_llh(x, r, penal_param)).reduce(lambda a, b: a + b)) / total
  while diff > 10e-7:
    gradient = (tf_idf.map(lambda x : compute_grad(x, r, penal_param)).reduce(lambda a, b: a + b)) / total
    r -= rate * gradient
    cur_llh = (tf_idf.map(lambda x : negative_llh(x, r, penal_param)).reduce(lambda a, b: a + b)) / total
    diff = abs(cur_llh - prev_llh)
    if cur_llh > prev_llh:
      rate = rate * 1.1
    else:
      rate = rate * .5
    prev_llh = cur_llh
  return r

# frst training your model on a small sample to speed up the process
tf_idf_sample = tf_idf.sample(True,0.2)
r = gd(np.zeros(20000),0.0001,tf_idf_sample)
r = gd(r,0.0001,tf_idf)

top_50 = np.argsort(r)[-50:]
top_50_words = [topWords[i][0] for i in reversed(top_50)]
print(top_50_words)

"""# Task3"""

corpus_test = sc.textFile ("s3://chrisjermainebucket/comp330_A5/TestingDataOneLinePerDoc.txt")
validLines_test = corpus_test.filter(lambda x : 'id' in x)
keyAndText_test = validLines_test.map(lambda x : (x[x.index('id="') + 4 : x.index('" url=')], x[x.index('">') + 2:]))

regex_test = re.compile('[^a-zA-Z]')
keyAndListOfWords_test = keyAndText_test.map(lambda x : (str(x[0]), regex_test.sub(' ', x[1]).lower().split()))
word_doc_test = keyAndListOfWords_test.flatMap(lambda x: ((j, str(x[0])) for j in x[1]))
word_idx_doc_test = dictionary.join(word_doc_test) # Using the training dictionary
doc_idx_test = word_idx_doc_test.map(lambda x : (x[1][1], x[1][0]))
doc_wordcnt_test = doc_idx_test.groupByKey().map(lambda x : (x[0], list(x[1]))).map(lambda x : (x[0], convert(x[1])))
doc_tf_test = doc_wordcnt_test.map(lambda x : (x[0], x[1] / np.sum(x[1])))
tf_idf_test = doc_tf_test.map(lambda x : (x[0], np.multiply(x[1], idf))) # Using the training idf
# Using mean and std from training data
tf_idf_test = tf_idf_test.map(lambda x : (x[0], np.nan_to_num((x[1] - mean) / (1000 * std)))).cache() # avoid potential divide by 0

y_pred_temp = tf_idf_test.map(lambda x : (x[0], [1] if r.dot(x[1]) > 0.0000029 else [0]))
y_true_temp = tf_idf_test.map(lambda x : (x[0], [1] if "AU" in str(x[0]) else [0]))
y_pred = y_pred_temp.values().reduce(lambda a, b : np.append(a, b))
y_true = y_true_temp.values().reduce(lambda a, b : np.append(a, b))
pred_right = y_pred.dot(y_true).sum()
true_num = float(y_true.sum())
pred_true = float(y_pred.sum())
recall = pred_right / true_num
precision = pred_right / pred_true
print(f"F1 score: {(2 * precision * recall) / (precision + recall)}")

false_pos = y_pred_temp.join(y_true_temp).filter(lambda x : x[1][0] == 1 and x[1][1] == 0).keys()
false_pos.top(3)
