from itertools import chain
import re
import lxml.etree as et


# FEATURES TO MAKE:
#   * Other non-consecutive subsets in general?
# * Number of other mentions on path


# NODESET:
# ===========

class NodeSet:
  """
  NodeSet objects are functions f : 2^T -> 2^T
  ---------------
  They are applied compositionally and lazily, by constructing an xpath query
  We use these to get the *subtree* or set of nodes that our indicicator features will
  operate over
  """
  def __init__(self):
    self.label = 'NODE_SET'
    self.xpath = '//*'

  def __repr__(self):
    return '<%s, xpath="%s">' % (self.label, self.xpath)


class Mention(NodeSet):
  """Gets candidate mention nodes"""
  def __init__(self, cid=0):
    self.label = 'MENTION'
    self.xpath = "//*[{%s}]" % str(cid)


class Keyword(NodeSet):
  """Gets keyword nodes"""
  def __init__(self, keyword, ns=None):
    self.label = 'KEYWORD-IN-%s' % ns.label if ns else 'KEYWORD'
    self.xpath = ns.xpath if ns else '//*'
    self.xpath += "[@word='%s']" % keyword


class LeftSiblings(NodeSet):
  """Gets preceding siblings"""
  def __init__(self, ns, w=3):
    self.label = 'LEFT-OF-%s' % ns.label
    self.xpath = '%s[1]/preceding-sibling::*[position() <= %s]' % (ns.xpath, w)


class RightSiblings(NodeSet):
  """Gets following siblings"""
  def __init__(self, ns, w=3):
    self.label = 'RIGHT-OF-%s' % ns.label
    self.xpath = '%s[1]/following-sibling::*[position() <= %s]' % (ns.xpath, w)


class Parents(NodeSet):
  """Gets parents of the node set"""
  def __init__(self, ns):
    self.label = 'PARENTS-OF-%s' % ns.label
    self.xpath = ns.xpath + '[1]/ancestor::*'


class Between(NodeSet):
  """
  Gets the nodes between two node sets
  Note: this requires some ugly xpath... could change this to non-xpath method
  """
  def __init__(self, ns1, ns2):
    self.label = 'BETWEEN-%s-and-%s' % (ns1.label, ns2.label)
    self.xpath = "{0}[1]/ancestor-or-self::*[count(. | {1}[1]/ancestor-or-self::*) = count({1}[1]/ancestor-or-self::*)][1]/descendant-or-self::*[(count(.{0}) = count({0})) or (count(.{1}) = count({1}))]".format(ns1.xpath, ns2.xpath)


class Filter(NodeSet):
  """
  Gets a subset of the nodes filtered by some node attribute
  Note the option to do exact match or starts with (could be expanded; useful for POS now...)
  """
  def __init__(self, ns, filter_attr, filter_by, starts_with=True):
    self.label = 'FILTER-BY(%s=%s):%s' % (filter_attr, filter_by, ns.label)
    temp = "[starts-with(@%s, '%s')]" if starts_with else "[@%s='%s']"
    self.xpath = ns.xpath + temp % (filter_attr, filter_by)


# INDICATOR:
# ===========

class Indicator:
  """
  Indicator objects are functions f : 2^T -> {0,1}^F
  ---------------
  Indicator objects take a NodeSet, an attibute or attributes, and apply some indicator
  function to the specified attributes of the NodeSet
  """
  def __init__(self, ns, attribs):
    self.ns = ns
    self.attribs = attribs

  def apply(self, root, cids, cid_attrib='word_idx'):
    """
    Apply the feature template to the xml tree provided
    A list of lists of candidate mention ids are passed in, as well as a cid_attrib
    These identify the candidate mentions refered to by index in Mention
    For example, cids=[[1,2]], cid_attrib='word_idx' will have mention 0 as the set of nodes
    that have word inde 1 and 2
    """
    # Sub in the candidate mention identifiers provided
    m = [" or ".join("@%s='%s'" % (cid_attrib, c) for c in cid) for cid in cids] 
    xpath = self.ns.xpath.format(*m)

    # Specifically handle single attrib or multiple attribs per node here
    attribs = re.split(r'\s*,\s*', self.attribs)
    if len(attribs) > 1:
      res = ['|'.join(str(node.get(a)) for a in attribs) for node in root.xpath(xpath)]
    else:
      res = map(str, root.xpath(xpath + '/@' + attribs[0]))

    # Only yield if non-zero result set; process through _get_features fn
    if len(res) > 0:
      for feat in self._get_features(res):
        yield '%s:%s[%s]' % ('|'.join(attribs).upper(), self.ns.label, feat)

  def _get_features(self, res):
    """
    Given a result set of attribute values, return a set of strings representing the features
    This should be the default method to replace for Indicator objects
    """
    return ['_'.join(res)]

  def print_apply(self, root, cids, cid_attrib='word_idx'):
    for feat in self.apply(root, cids, cid_attrib):
      print feat
  
  def __repr__(self):
    return '<%s:%s:%s, xpath="%s">' % (self.__class__.__name__, self.attribs, self.ns.label, self.ns.xpath)


class Ngrams(Indicator):
  """
  Return indicator features over the ngrams of a result set
  If ng arg is an int, will get ngrams of *exactly* this length
  If ng arg is a list/tuple, will get all ngrams of this range, *inclusive*
  """
  def __init__(self, ns, attribs, ng):
    self.ns = ns
    self.attribs = attribs
    if (type(ng) == int and ng > 0) or (type(ng) in [list, tuple] and ng[0] > 0):
      self.ng = ng
    else:
      raise ValueError("Improper ngram range: %s" % ng)

  def _get_features(self, res):
    if type(self.ng) == int:
      r = [self.ng - 1]
    else:
      r = range(self.ng[0] - 1, min(len(res), self.ng[1]))
    return chain.from_iterable(['_'.join(res[s:s+l+1]) for s in range(len(res)-l)] for l in r)


class RightNgrams(Indicator):
  """Return all the ngrams which start at position 0"""
  def _get_features(self, res):
    return ['_'.join(res[:l]) for l in range(1, len(res)+1)]
    

class LeftNgrams(Indicator):
  """Return all the ngrams which start at position 0"""
  def _get_features(self, res):
    return ['_'.join(res[l:]) for l in range(len(res))]
    

class Regexp(Indicator):
  """
  Return indicator features defined by regular expressions applied to the 
  concatenation of the result set strings
  """
  def __init__(self, ns, attribs, rgx, rgx_label, sep=' '):
    self.ns = ns
    self.attribs = attribs
    self.rgx = rgx
    self.rgx_label = rgx_label
    self.sep = sep

  # TODO: Sort by word order...
  def _get_features(self, res):
    yield 'RGX:%s=%s' % (self.rgx_label, re.search(self.rgx, self.sep.join(res)) is not None)


# COMBINATOR:
# ===========

class Combinator:
  """
  Combinator objects are functions f : {0,1}^F x {0,1}^F -> {0,1}^F
  ---------------
  Combinator objects take two (or more?) Indicator objects and map to feature space
  """
  def __init__(self, ind1, ind2):
    self.ind1 = ind1
    self.ind2 = ind2

  def apply(self, root, cids, cid_attrib):
    return self.ind1.apply(root, cids, cid_attrib)

  def print_apply(self, root, cids, cid_attrib):
    return self.apply(root, cids, cid_attrib)
  

class Combinations(Combinator):
  """Generates all *pairs* of features"""
  def apply(self, root, cids, cid_attrib):
    for f1 in self.ind1.apply(root, cids, cid_attrib):
      for f2 in self.ind2.apply(root, cids, cid_attrib):
        yield '%s+%s' % (f1, f2)


# Compile Operator: Compiles a set of feature templates
# =====================================================

class Compile:
  """
  Compiles a set of functions f_i : 2^T -> {0,1}^F_i to a single function 2^T -> {0,1}^F
  where F <= \sum_i F_i
  i.e. we can do filtering and/or merging at this point (?)
  """
  def __init__(self, ops):
    self.ops = ops

  def apply(self, root, cids, cid_attrib='word_idx'):
    # Ensure that root is parsed
    if type(root) == str:
      root = et.fromstring(root)

    # Apply the feature templates
    for op in ops:
     
      # Accept iterators or single operators
      if hasattr(op, '__iter__'):
        for o in op:
          for f in o.apply(root, cids, cid_attrib):
            yield f
      else:
        for f in op.apply(root, cids, cid_attrib):
          yield f
  
  def apply_mention(self, root, mention_idxs):
    return self.apply(self, root, [mention_idxs])
  
  def apply_relation(self, root, mention1_idxs, mention2_idxs):
    return self.apply(self, root, [mention1_idxs, mention2_idxs])

   

# TODO: "Between" as dep path vs. sentence...

# TODO: Get all DDLIB features re-implemented...

# TODO: CONFIG file...?

# TODO: Features such as- on same level? < k hops apart? etc.

# TODO: Think about doc-level features and how to implement this

# TODO: Table features

# TODO: Stopwords