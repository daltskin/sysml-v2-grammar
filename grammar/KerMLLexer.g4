/*
 * KerML ANTLR4 Grammar
 * Derived from the OMG KerML specification (KEBNF format).
 * Source: https://github.com/Systems-Modeling/SysML-v2-Release
 * Generator: https://github.com/daltskin/sysml-v2-grammar
 * License: MIT
 */

lexer grammar KerMLLexer;

// $antlr-format alignTrailingComments true, columnLimit 150, useTab false
// $antlr-format allowShortRulesOnASingleLine false, allowShortBlocksOnASingleLine true
// $antlr-format alignSemicolons hanging, alignColons hanging
// $antlr-format minEmptyLines 1, maxEmptyLinesToKeep 1, reflowComments false

// Keywords
ABOUT : 'about' ;
ABSTRACT : 'abstract' ;
ALIAS : 'alias' ;
ALL : 'all' ;
AND : 'and' ;
AS : 'as' ;
ASSOC : 'assoc' ;
BEHAVIOR : 'behavior' ;
BINDING : 'binding' ;
BOOL : 'bool' ;
BY : 'by' ;
CHAINS : 'chains' ;
CLASS : 'class' ;
CLASSIFIER : 'classifier' ;
COMMENT : 'comment' ;
COMPOSITE : 'composite' ;
CONJUGATE : 'conjugate' ;
CONJUGATES : 'conjugates' ;
CONJUGATION : 'conjugation' ;
CONNECTOR : 'connector' ;
CONST : 'const' ;
CROSSES : 'crosses' ;
DATATYPE : 'datatype' ;
DEFAULT : 'default' ;
DEPENDENCY : 'dependency' ;
DERIVED : 'derived' ;
DIFFERENCES : 'differences' ;
DISJOINING : 'disjoining' ;
DISJOINT : 'disjoint' ;
DOC : 'doc' ;
ELSE : 'else' ;
END : 'end' ;
EXPR : 'expr' ;
FALSE : 'false' ;
FEATURE : 'feature' ;
FEATURED : 'featured' ;
FEATURING : 'featuring' ;
FILTER : 'filter' ;
FIRST : 'first' ;
FLOW : 'flow' ;
FOR : 'for' ;
FROM : 'from' ;
FUNCTION : 'function' ;
HASTYPE : 'hastype' ;
IF : 'if' ;
IMPLIES : 'implies' ;
IMPORT : 'import' ;
IN : 'in' ;
INOUT : 'inout' ;
INTERACTION : 'interaction' ;
INTERSECTS : 'intersects' ;
INV : 'inv' ;
INVERSE : 'inverse' ;
INVERTING : 'inverting' ;
ISTYPE : 'istype' ;
LANGUAGE : 'language' ;
LIBRARY : 'library' ;
LOCALE : 'locale' ;
MEMBER : 'member' ;
META : 'meta' ;
METACLASS : 'metaclass' ;
METADATA : 'metadata' ;
MULTIPLICITY : 'multiplicity' ;
NAMESPACE : 'namespace' ;
NEW : 'new' ;
NONUNIQUE : 'nonunique' ;
NOT : 'not' ;
NULL : 'null' ;
OF : 'of' ;
OR : 'or' ;
ORDERED : 'ordered' ;
OUT : 'out' ;
PACKAGE : 'package' ;
PORTION : 'portion' ;
PREDICATE : 'predicate' ;
PRIVATE : 'private' ;
PROTECTED : 'protected' ;
PUBLIC : 'public' ;
REDEFINES : 'redefines' ;
REDEFINITION : 'redefinition' ;
REFERENCES : 'references' ;
REP : 'rep' ;
RETURN : 'return' ;
SPECIALIZATION : 'specialization' ;
SPECIALIZES : 'specializes' ;
STANDARD : 'standard' ;
STEP : 'step' ;
STRUCT : 'struct' ;
SUBCLASSIFIER : 'subclassifier' ;
SUBSET : 'subset' ;
SUBSETS : 'subsets' ;
SUBTYPE : 'subtype' ;
SUCCESSION : 'succession' ;
THEN : 'then' ;
TO : 'to' ;
TRUE : 'true' ;
TYPE : 'type' ;
TYPED : 'typed' ;
TYPING : 'typing' ;
UNIONS : 'unions' ;
VAR : 'var' ;
XOR : 'xor' ;

// Operators and punctuation
BANG_EQ_EQ : '!==' ;
COLON_COLON_GT : '::>' ;
COLON_GT_GT : ':>>' ;
EQ_EQ_EQ : '===' ;
BANG_EQ : '!=' ;
STAR_STAR : '**' ;
ARROW : '->' ;
DOT_DOT : '..' ;
DOT_QUESTION : '.?' ;
COLON_COLON : '::' ;
COLON_EQ : ':=' ;
COLON_GT : ':>' ;
LE : '<=' ;
EQ_EQ : '==' ;
FAT_ARROW : '=>' ;
GE : '>=' ;
QUESTION_QUESTION : '??' ;
AT_AT : '@@' ;
HASH : '#' ;
DOLLAR : '$' ;
PERCENT : '%' ;
AMP : '&' ;
LPAREN : '(' ;
RPAREN : ')' ;
STAR : '*' ;
PLUS : '+' ;
COMMA : ',' ;
MINUS : '-' ;
DOT : '.' ;
SLASH : '/' ;
COLON : ':' ;
SEMI : ';' ;
LT : '<' ;
EQ : '=' ;
GT : '>' ;
QUESTION : '?' ;
AT_SIGN : '@' ;
LBRACK : '[' ;
RBRACK : ']' ;
CARET : '^' ;
LBRACE : '{' ;
PIPE : '|' ;
RBRACE : '}' ;
TILDE : '~' ;

// Identifiers
IDENTIFIER : [a-zA-Z_] [a-zA-Z0-9_]* ;

// String literals
STRING : '\'' ( '\\' . | ~['\\] )* '\'' ;
DOUBLE_STRING : '"' ( '\\' . | ~["\\] )* '"' ;

// Numeric literals
INTEGER : [0-9]+ ;
REAL : [0-9]* '.' [0-9]+ ( [eE] [+-]? [0-9]+ )? | [0-9]+ [eE] [+-]? [0-9]+ ;

// Comments
// REGULAR_COMMENT also matches //* ... */ (OMG block-comment-out convention).
REGULAR_COMMENT : '/*' .*? '*/' | '//*' .*? '*/' ;
// SINGLE_LINE_NOTE: '//' followed by non-'*' content (to avoid consuming
// //* ... */ block comments which are handled by REGULAR_COMMENT).
// A bare '//' at end of line is handled by the second rule.
SINGLE_LINE_NOTE : '//' ~[*\r\n] ~[\r\n]* -> skip ;
BARE_LINE_COMMENT : '//' -> skip ;

// Whitespace
WS : [ \t\r\n]+ -> skip ;