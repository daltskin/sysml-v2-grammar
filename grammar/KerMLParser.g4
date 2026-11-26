/*
 * KerML ANTLR4 Grammar
 * Derived from the OMG KerML specification (KEBNF format).
 * Source: https://github.com/Systems-Modeling/SysML-v2-Release
 * Generator: https://github.com/daltskin/sysml-v2-grammar
 * License: MIT
 */

parser grammar KerMLParser;

options {
    tokenVocab = KerMLLexer;
}

// $antlr-format alignTrailingComments true, columnLimit 150, useTab false
// $antlr-format allowShortRulesOnASingleLine false, allowShortBlocksOnASingleLine true
// $antlr-format alignSemicolons hanging, alignColons hanging
// $antlr-format minEmptyLines 1, maxEmptyLinesToKeep 1, reflowComments false

// ===== Expression rules (precedence-climbing) =====

ownedExpression
    : ( ISTYPE | HASTYPE | AT_SIGN | AS ) typeReference
    | ALL typeReference
    | ( PLUS | MINUS | TILDE | NOT ) ownedExpression
    | <assoc=right> ownedExpression ( STAR_STAR | CARET ) ownedExpression
    | ownedExpression ( STAR | SLASH | PERCENT ) ownedExpression
    | ownedExpression ( PLUS | MINUS ) ownedExpression
    | ownedExpression DOT_DOT ownedExpression
    | ownedExpression ( LT | GT | LE | GE ) ownedExpression
    | ownedExpression ( ISTYPE | HASTYPE | AT_SIGN ) typeReference
    | ownedExpression AS typeReference
    | ownedExpression ( EQ_EQ | BANG_EQ | EQ_EQ_EQ | BANG_EQ_EQ ) ownedExpression
    | ownedExpression ( AMP | AND ) ownedExpression
    | ownedExpression XOR ownedExpression
    | ownedExpression ( PIPE | OR ) ownedExpression
    | ownedExpression IMPLIES ownedExpression
    | ownedExpression QUESTION_QUESTION ownedExpression
    | primaryExpression
    | IF ownedExpression QUESTION ownedExpression ELSE ownedExpression
    ;

primaryExpression
    : qualifiedName ( AT_AT | META ) typeReference
    | baseExpression
      ( DOT featureChainMember )?
      (
        ( LBRACK sequenceExpressionList RBRACK
        | HASH LPAREN sequenceExpressionList RPAREN
        | ARROW featureChainMember ( bodyExpression | qualifiedName | argumentList )
        | DOT bodyExpression
        | DOT_QUESTION bodyExpression
        )
        ( DOT featureChainMember )?
      )*
    ;

typeReference
    : qualifiedName
    ;

sequenceExpressionList
    : ownedExpression ( COMMA ownedExpression )* COMMA?
    ;

baseExpression
    : nullExpression
    | REGULAR_COMMENT   // ignore block comments used as expression placeholders
    | literalExpression
    | qualifiedName DOT qualifiedName ( DOT qualifiedName )* argumentList
    | qualifiedName ( argumentList | DOT METADATA )?   // merged featureRef/metadataAccess/invocation
    | constructorExpression
    | bodyExpression
    | LPAREN sequenceExpressionList? RPAREN
    ;

nullExpression
    : NULL
    ;

featureReferenceExpression
    : qualifiedName
    ;

constructorExpression
    : NEW featureChainMember argumentList
    ;

bodyExpression
    : LBRACE functionBodyPart RBRACE
    ;

argumentList
    : LPAREN ( positionalArgumentList | namedArgumentList )? RPAREN
    ;

positionalArgumentList
    : ownedExpression ( COMMA ownedExpression )*
    ;

namedArgumentList
    : namedArgument ( COMMA namedArgument )*
    ;

namedArgument
    : qualifiedName EQ ownedExpression
    ;

literalExpression
    : literalBoolean
    | literalString
    | literalInteger
    | literalReal
    | literalInfinity
    ;

literalBoolean : TRUE | FALSE ;
literalString : DOUBLE_STRING ;
literalInteger : INTEGER ;
literalReal : REAL ;
literalInfinity : STAR ;

// ===== Name rule (Identifier or UnrestrictedName) =====

name
    : IDENTIFIER
    | STRING
    ;

// ===== Parser rules =====

identification
    : LT name GT name
    | LT name GT
    | name
    ;

relationshipBody
    : SEMI
    | LBRACE relationshipOwnedElement* RBRACE
    ;

relationshipOwnedElement
    : ownedRelatedElement
    | ownedAnnotation
    ;

ownedRelatedElement
    : nonFeatureElement
    | featureElement
    ;

dependency
    : ( prefixMetadataAnnotation )* DEPENDENCY ( identification? FROM )? qualifiedName ( COMMA qualifiedName )* TO qualifiedName ( COMMA qualifiedName )* relationshipBody
    ;

annotation
    : qualifiedName
    ;

ownedAnnotation
    : annotatingElement
    ;

annotatingElement
    : comment
    | documentation
    | textualRepresentation
    | metadataFeature
    ;

comment
    : ( COMMENT identification? ( ABOUT annotation ( COMMA annotation )* )? )? ( LOCALE DOUBLE_STRING )? REGULAR_COMMENT
    ;

documentation
    : DOC identification? ( LOCALE DOUBLE_STRING )? REGULAR_COMMENT
    ;

textualRepresentation
    : ( REP identification? )? LANGUAGE DOUBLE_STRING REGULAR_COMMENT
    ;

rootNamespace
    : namespaceBodyElement* EOF
    ;

namespace
    : ( prefixMetadataMember )* namespaceDeclaration namespaceBody
    ;

namespaceDeclaration
    : NAMESPACE identification?
    ;

namespaceBody
    : SEMI
    | LBRACE namespaceBodyElement* RBRACE
    ;

namespaceBodyElement
    : namespaceMember
    | aliasMember
    | importRule
    ;

memberPrefix
    : ( visibilityIndicator )?
    ;

visibilityIndicator
    : PUBLIC
    | PRIVATE
    | PROTECTED
    ;

namespaceMember
    : nonFeatureMember
    | namespaceFeatureMember
    ;

nonFeatureMember
    : memberPrefix memberElement
    ;

namespaceFeatureMember
    : memberPrefix featureElement
    ;

aliasMember
    : memberPrefix ALIAS ( LT name GT )? ( name )? FOR qualifiedName relationshipBody
    ;

qualifiedName
    : ( DOLLAR COLON_COLON )? ( name COLON_COLON )* name
    ;

importRule
    : visibilityIndicator IMPORT ( ALL )? importDeclaration relationshipBody
    ;

importDeclaration
    : membershipImport
    | namespaceImport
    ;

membershipImport
    : qualifiedName ( COLON_COLON STAR_STAR )?
    ;

namespaceImport
    : qualifiedName COLON_COLON STAR ( COLON_COLON STAR_STAR )?
    | filterPackage
    ;

filterPackage
    : filterPackageImportDeclaration ( filterPackageMember )+
    ;

filterPackageMember
    : LBRACK ownedExpression RBRACK
    ;

memberElement
    : annotatingElement
    | nonFeatureElement
    ;

nonFeatureElement
    : dependency
    | namespace
    | type
    | classifier
    | dataType
    | class
    | structure
    | metaclass
    | association
    | associationStructure
    | interaction
    | behavior
    | function
    | predicate
    | multiplicity
    | package
    | libraryPackage
    | specialization
    | conjugation
    | subclassification
    | disjoining
    | featureInverting
    | featureTyping
    | subsetting
    | redefinition
    | typeFeaturing
    ;

featureElement
    : feature
    | step
    | expression
    | booleanExpression
    | invariant
    | connector
    | bindingConnector
    | succession
    | flow
    | successionFlow
    ;

type
    : typePrefix TYPE typeDeclaration typeBody
    ;

typePrefix
    : ( ABSTRACT )? ( prefixMetadataMember )*
    ;

typeDeclaration
    : ( ALL )? identification? ( ownedMultiplicity )? ( specializationPart | conjugationPart )+ typeRelationshipPart*
    ;

specializationPart
    : ( COLON_GT | SPECIALIZES ) ownedSpecialization ( COMMA ownedSpecialization )*
    ;

conjugationPart
    : ( TILDE | CONJUGATES ) ownedConjugation
    ;

typeRelationshipPart
    : disjoiningPart
    | unioningPart
    | intersectingPart
    | differencingPart
    ;

disjoiningPart
    : DISJOINT FROM ownedDisjoining ( COMMA ownedDisjoining )*
    ;

unioningPart
    : UNIONS unioning ( COMMA unioning )*
    ;

intersectingPart
    : INTERSECTS intersecting ( COMMA intersecting )*
    ;

differencingPart
    : DIFFERENCES differencing ( COMMA differencing )*
    ;

typeBody
    : SEMI
    | LBRACE typeBodyElement* RBRACE
    ;

typeBodyElement
    : nonFeatureMember
    | featureMember
    | aliasMember
    | importRule
    ;

specialization
    : ( SPECIALIZATION identification? )? SUBTYPE specificType ( COLON_GT | SPECIALIZES ) generalType relationshipBody
    ;

ownedSpecialization
    : generalType
    ;

specificType
    : qualifiedName ( DOT qualifiedName )*
    ;

generalType
    : qualifiedName ( DOT qualifiedName )*
    ;

conjugation
    : ( CONJUGATION identification? )? CONJUGATE qualifiedName ( DOT qualifiedName )* ( TILDE | CONJUGATES ) qualifiedName ( DOT qualifiedName )* relationshipBody
    ;

ownedConjugation
    : qualifiedName ( DOT qualifiedName )*
    ;

disjoining
    : ( DISJOINING identification? )? DISJOINT qualifiedName ( DOT qualifiedName )* FROM qualifiedName ( DOT qualifiedName )* relationshipBody
    ;

ownedDisjoining
    : qualifiedName ( DOT qualifiedName )*
    ;

unioning
    : qualifiedName ( DOT qualifiedName )*
    ;

intersecting
    : qualifiedName ( DOT qualifiedName )*
    ;

differencing
    : qualifiedName ( DOT qualifiedName )*
    ;

featureMember
    : typeFeatureMember
    | ownedFeatureMember
    ;

typeFeatureMember
    : memberPrefix MEMBER featureElement
    ;

ownedFeatureMember
    : memberPrefix featureElement
    ;

classifier
    : typePrefix CLASSIFIER classifierDeclaration typeBody
    ;

classifierDeclaration
    : ( ALL )? identification? ( ownedMultiplicity )? ( superclassingPart | conjugationPart )? typeRelationshipPart*
    ;

superclassingPart
    : ( COLON_GT | SPECIALIZES ) ownedSubclassification ( COMMA ownedSubclassification )*
    ;

subclassification
    : ( SPECIALIZATION identification? )? SUBCLASSIFIER qualifiedName ( COLON_GT | SPECIALIZES ) qualifiedName relationshipBody
    ;

ownedSubclassification
    : qualifiedName
    ;

feature
    : ( featurePrefix ( FEATURE | prefixMetadataMember ) featureDeclaration? | ( endFeaturePrefix | basicFeaturePrefix ) featureDeclaration ) valuePart? typeBody
    ;

endFeaturePrefix
    : ( CONST )? END
    ;

basicFeaturePrefix
    : ( featureDirection )? ( DERIVED )? ( ABSTRACT )? ( COMPOSITE | PORTION )? ( VAR | CONST )?
    ;

featurePrefix
    : ( endFeaturePrefix ( ownedCrossFeatureMember )? | basicFeaturePrefix ) ( prefixMetadataMember )*
    ;

ownedCrossFeatureMember
    : ownedCrossFeature
    ;

ownedCrossFeature
    : basicFeaturePrefix featureDeclaration
    ;

featureDirection
    : IN
    | OUT
    | INOUT
    ;

featureDeclaration
    : ( ALL )? ( featureIdentification ( featureSpecializationPart | conjugationPart )? | featureSpecializationPart | conjugationPart ) featureRelationshipPart*
    ;

featureIdentification
    : LT name GT ( name )?
    | name
    ;

featureRelationshipPart
    : typeRelationshipPart
    | chainingPart
    | invertingPart
    | typeFeaturingPart
    ;

chainingPart
    : CHAINS qualifiedName ( DOT qualifiedName )*
    ;

invertingPart
    : INVERSE OF ownedFeatureInverting
    ;

typeFeaturingPart
    : FEATURED BY ownedTypeFeaturing ( COMMA ownedTypeFeaturing )*
    ;

featureSpecializationPart
    : featureSpecialization+ multiplicityPart? featureSpecialization*
    | multiplicityPart featureSpecialization*
    ;

multiplicityPart
    : ownedMultiplicity ( ORDERED ( NONUNIQUE )? | NONUNIQUE ( ORDERED )? )?
    | ( ORDERED ( NONUNIQUE )? | NONUNIQUE ( ORDERED )? )
    ;

featureSpecialization
    : typings
    | subsettings
    | references
    | crosses
    | redefinitions
    ;

typings
    : typedBy ( COMMA ownedFeatureTyping )*
    ;

typedBy
    : ( COLON | TYPED BY ) ownedFeatureTyping
    ;

subsettings
    : subsets ( COMMA ownedSubsetting )*
    ;

subsets
    : ( COLON_GT | SUBSETS ) ownedSubsetting
    ;

references
    : ( COLON_COLON_GT | REFERENCES ) ownedReferenceSubsetting
    ;

crosses
    : ( FAT_ARROW | CROSSES ) ownedCrossSubsetting
    ;

redefinitions
    : redefines ( COMMA ownedRedefinition )*
    ;

redefines
    : ( COLON_GT_GT | REDEFINES ) ownedRedefinition
    ;

featureTyping
    : ( SPECIALIZATION identification? )? TYPING qualifiedName ( COLON | TYPED BY ) generalType relationshipBody
    ;

ownedFeatureTyping
    : generalType
    ;

subsetting
    : ( SPECIALIZATION identification? )? SUBSET specificType ( COLON_GT | SUBSETS ) generalType relationshipBody
    ;

ownedSubsetting
    : generalType
    ;

ownedReferenceSubsetting
    : generalType
    ;

ownedCrossSubsetting
    : generalType
    ;

redefinition
    : ( SPECIALIZATION identification? )? REDEFINITION specificType ( COLON_GT_GT | REDEFINES ) generalType relationshipBody
    ;

ownedRedefinition
    : generalType
    ;

featureChain
    : ownedFeatureChaining ( DOT ownedFeatureChaining )+
    ;

ownedFeatureChaining
    : qualifiedName
    ;

featureInverting
    : ( INVERTING identification? )? INVERSE qualifiedName ( DOT qualifiedName )* OF qualifiedName ( DOT qualifiedName )* relationshipBody
    ;

ownedFeatureInverting
    : qualifiedName ( DOT qualifiedName )*
    ;

typeFeaturing
    : FEATURING ( identification? OF )? qualifiedName BY qualifiedName relationshipBody
    ;

ownedTypeFeaturing
    : qualifiedName
    ;

dataType
    : typePrefix DATATYPE classifierDeclaration typeBody
    ;

class
    : typePrefix CLASS classifierDeclaration typeBody
    ;

structure
    : typePrefix STRUCT classifierDeclaration typeBody
    ;

association
    : typePrefix ASSOC classifierDeclaration typeBody
    ;

associationStructure
    : typePrefix ASSOC STRUCT classifierDeclaration typeBody
    ;

connector
    : featurePrefix CONNECTOR ( featureDeclaration? valuePart? | connectorDeclaration ) typeBody
    ;

connectorDeclaration
    : binaryConnectorDeclaration
    | naryConnectorDeclaration
    ;

binaryConnectorDeclaration
    : ( featureDeclaration? FROM | ALL FROM? )? connectorEndMember TO connectorEndMember
    ;

naryConnectorDeclaration
    : featureDeclaration? LPAREN connectorEndMember COMMA connectorEndMember ( COMMA connectorEndMember )* RPAREN
    ;

connectorEndMember
    : connectorEnd
    ;

connectorEnd
    : ( ownedCrossMultiplicityMember )? ( name ( COLON_COLON_GT | REFERENCES ) )? ownedReferenceSubsetting
    ;

ownedCrossMultiplicityMember
    : ownedCrossMultiplicity
    ;

ownedCrossMultiplicity
    : ownedMultiplicity
    ;

bindingConnector
    : featurePrefix BINDING bindingConnectorDeclaration typeBody
    ;

bindingConnectorDeclaration
    : featureDeclaration ( OF connectorEndMember EQ connectorEndMember )?
    | ( ALL )? ( OF? connectorEndMember EQ connectorEndMember )?
    ;

succession
    : featurePrefix SUCCESSION successionDeclaration typeBody
    ;

successionDeclaration
    : featureDeclaration ( FIRST connectorEndMember THEN connectorEndMember )?
    | ( ALL )? ( FIRST? connectorEndMember THEN connectorEndMember )?
    ;

behavior
    : typePrefix BEHAVIOR classifierDeclaration typeBody
    ;

step
    : featurePrefix STEP featureDeclaration valuePart? typeBody
    ;

function
    : typePrefix FUNCTION classifierDeclaration functionBody
    ;

functionBody
    : SEMI
    | LBRACE functionBodyPart RBRACE
    ;

functionBodyPart
    : ( typeBodyElement | returnFeatureMember )* ( resultExpressionMember )?
    ;

returnFeatureMember
    : memberPrefix RETURN featureElement
    ;

resultExpressionMember
    : memberPrefix ownedExpression
    ;

expression
    : featurePrefix EXPR featureDeclaration valuePart? functionBody
    ;

predicate
    : typePrefix PREDICATE classifierDeclaration functionBody
    ;

booleanExpression
    : featurePrefix BOOL featureDeclaration valuePart? functionBody
    ;

invariant
    : featurePrefix INV ( TRUE | FALSE )? featureDeclaration? valuePart? functionBody
    ;

featureChainMember
    : featureReferenceMember
    | ownedFeatureChainMember
    ;

ownedFeatureChainMember
    : featureChain
    ;

featureReferenceMember
    : featureReference
    ;

featureReference
    : qualifiedName
    ;

interaction
    : typePrefix INTERACTION classifierDeclaration typeBody
    ;

flow
    : featurePrefix FLOW flowDeclaration typeBody
    ;

successionFlow
    : featurePrefix SUCCESSION FLOW flowDeclaration typeBody
    ;

flowDeclaration
    : featureDeclaration valuePart? ( OF payloadFeatureMember )? ( FROM flowEndMember TO flowEndMember )?
    | ( ALL )? flowEndMember TO flowEndMember
    ;

payloadFeatureMember
    : payloadFeature
    ;

payloadFeature
    : identification payloadFeatureSpecializationPart valuePart?
    | identification valuePart
    | ownedFeatureTyping ( ownedMultiplicity )?
    | ownedMultiplicity ownedFeatureTyping
    ;

payloadFeatureSpecializationPart
    : featureSpecialization+ multiplicityPart? featureSpecialization*
    | multiplicityPart featureSpecialization+
    ;

flowEndMember
    : flowEnd
    ;

flowEnd
    : ( ownedReferenceSubsetting DOT )? flowFeatureMember
    ;

flowFeatureMember
    : flowFeature
    ;

flowFeature
    : flowFeatureRedefinition
    ;

flowFeatureRedefinition
    : qualifiedName
    ;

valuePart
    : featureValue
    ;

featureValue
    : ( EQ | COLON_EQ | DEFAULT ( EQ | COLON_EQ )? ) ownedExpression
    ;

multiplicity
    : multiplicitySubset
    | multiplicityRange
    ;

multiplicitySubset
    : MULTIPLICITY identification? subsets typeBody
    ;

multiplicityRange
    : MULTIPLICITY identification? multiplicityBounds typeBody
    ;

ownedMultiplicity
    : ownedMultiplicityRange
    ;

ownedMultiplicityRange
    : multiplicityBounds
    ;

multiplicityBounds
    : LBRACK ( multiplicityExpressionMember DOT_DOT )? multiplicityExpressionMember RBRACK
    ;

multiplicityExpressionMember
    : ( literalExpression | featureReferenceExpression )
    ;

metaclass
    : typePrefix METACLASS classifierDeclaration typeBody
    ;

prefixMetadataAnnotation
    : HASH prefixMetadataFeature
    ;

prefixMetadataMember
    : HASH prefixMetadataFeature
    ;

prefixMetadataFeature
    : ownedFeatureTyping
    ;

metadataFeature
    : ( prefixMetadataMember )* ( AT_SIGN | METADATA ) metadataFeatureDeclaration ( ABOUT annotation ( COMMA annotation )* )? metadataBody
    ;

metadataFeatureDeclaration
    : ( identification? ( COLON | TYPED BY ) )? ownedFeatureTyping
    ;

metadataBody
    : SEMI
    | LBRACE ( metadataBodyElement )* RBRACE
    ;

metadataBodyElement
    : nonFeatureMember
    | metadataBodyFeatureMember
    | aliasMember
    | importRule
    ;

metadataBodyFeatureMember
    : metadataBodyFeature
    ;

metadataBodyFeature
    : FEATURE? ( COLON_GT_GT | REDEFINES )? ownedRedefinition featureSpecializationPart? valuePart? metadataBody
    ;

package
    : ( prefixMetadataMember )* packageDeclaration packageBody
    ;

libraryPackage
    : ( STANDARD )? LIBRARY ( prefixMetadataMember )* packageDeclaration packageBody
    ;

packageDeclaration
    : PACKAGE identification?
    ;

packageBody
    : SEMI
    | LBRACE ( namespaceBodyElement | elementFilterMember )* RBRACE
    ;

elementFilterMember
    : memberPrefix FILTER ownedExpression SEMI
    ;

filterPackageImportDeclaration
    : membershipImport
    | namespaceImportDirect
    ;

namespaceImportDirect
    : qualifiedName COLON_COLON STAR ( COLON_COLON STAR_STAR )?
    ;

// ===== Stub rules for undefined references =====
// These rules are referenced in the spec but not fully defined.
// They need manual review and completion.

