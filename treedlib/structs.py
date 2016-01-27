import json
import os
import re
import lxml.etree as et

# This should be set by the lib wrapper __init__.py file
APP_HOME = os.environ["TREEDLIB_LIB"]

# Load IPython display functionality libs if possible i.e. if in IPython
try:
  from IPython.core.display import display_html, HTML, display_javascript, Javascript
except:
  pass

class XMLTree:
  """
  A generic tree representation which takes XML as input
  Includes subroutines for conversion to JSON & for visualization based on js form
  """
  def __init__(self, xml_root):
    """Calls subroutines to generate JSON form of XML input"""
    self.root = xml_root

    # create a unique id for e.g. canvas id in notebook
    self.id = str(abs(hash(self.to_str())))

  def _to_json(self, root):
    js = {
      'attrib': dict(root.attrib),
      'children': []
    }
    for i,c in enumerate(root):
      js['children'].append(self._to_json(c))
    return js

  def to_json(self):
    return self._to_json(self.root)

  def to_str(self):
    return et.tostring(self.root)

  def render_tree(self):
    """
    Renders d3 visualization of the d3 tree, for IPython notebook display
    Depends on html/js files in vis/ directory, which is assumed to be in same dir...
    """
    # HTML
    html = open('%s/vis/tree-chart.html' % APP_HOME).read() % self.id
    display_html(HTML(data=html))

    # JS
    JS_LIBS = ["http://d3js.org/d3.v3.min.js"]
    js = open('%s/vis/tree-chart.js' % APP_HOME).read() % (json.dumps(self.to_json()), self.id)
    display_javascript(Javascript(data=js, lib=JS_LIBS))


def corenlp_to_xmltree(s, prune_root=True):
  """
  Transforms an object with CoreNLP dep_path and dep_parent attributes into an XMLTree
  Will include elements of any array having the same dimensiion as dep_* as node attributes
  Also adds special word_idx attribute corresponding to original sequence order in sentence
  """
  # Parse recursively
  root = corenlp_to_xmltree_sub(s, 0)

  # Often the return tree will have several roots, where one is the actual root
  # And the rest are just singletons not included in the dep tree parse...
  # We optionally remove these singletons and then collapse the root if only one child left
  if prune_root:
    for c in root:
      if len(c) == 0:
        root.remove(c)
    if len(root) == 1:
      root = root.findall("./*")[0]
  return XMLTree(root)

def corenlp_to_xmltree_sub(s, rid=0):
  i = rid - 1
  attrib = {}

  # Get the object as a list of k,v tuples
  try:
    tups = s._asdict().iteritems()
  except AttributeError:
    tups = dict(s).iteritems()

  # Add all attributes
  if i >= 0:
    for k,v in filter(lambda x : type(x[1]) == list, tups):
      if v[i] is not None:
        attrib[singular(k)] = ''.join(c for c in str(v[i]) if ord(c) < 128)

    # Add word_idx if not present
    if 'word_idx' not in attrib:
      attrib['word_idx'] = str(i)

  # Build tree recursively
  root = et.Element('node', attrib=attrib)
  for i,d in enumerate(s.dep_parents):
    if d == rid:
      root.append(corenlp_to_xmltree_sub(s, i+1))
  return root

def singular(s):
  """Get singular form of word s (crudely)"""
  return re.sub(r'e?s$', '', s, flags=re.I)


def html_table_to_xmltree(html):
  """HTML/XML table to XMLTree object"""
  node = et.fromstring(re.sub(r'>\s+<', '><', html.strip()))
  xml = html_table_to_xmltree_sub(node)
  return XMLTree(xml)

def html_table_to_xmltree_sub(node):
  """
  Take the XML/HTML table and convert each word in leaf nodes into its own node
  Note: Ideally this text would be run through CoreNLP?
  """
  # Split text into Token nodes
  # NOTE: very basic token splitting here... (to run through CoreNLP?)
  if node.text is not None:
    for tok in re.split(r'\s+', node.text):
      node.append(et.Element('token', attrib={'word':tok}))
  
  # Recursively append children
  for c in node:
    node.append(html_table_to_xmltree_sub(c))
  return node
