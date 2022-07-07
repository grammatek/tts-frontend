"""
Handles the communication with the normalizer module. The result of the normalize methods in normalizer_manager is
a list of Tokens, composed from the original tokens, a cleaned, tokenized version, and the normalized
version. The list will also possibly contain TagTokens, created from SSML-tags inserted by the cleaner module or
the normalizer module, as well as pos-tags delivered by the normalizer module.
"""
import difflib

from typing import Tuple
from .tokens import Normalized, TagToken
from .tokens_manager import extract_sentences
from .linked_tokens import LinkedTokens
#production
from regina_normalizer import abbr_functions
from regina_normalizer import number_functions
#local testing
#from src.regina_normalizer.regina_normalizer_pkg.regina_normalizer import abbr_functions
#from src.regina_normalizer.regina_normalizer_pkg.regina_normalizer import number_functions


class NormalizerManager:

    def normalize_token_list(self, token_list: list) -> list:
        """Normalizes the text represented by the token list,
        assembles a new list of Tokens and TagTokens, if any are in the token list or if tags are added
        during normalization, each Token enriched by the normalizer results."""

        pre_normalized = []
        final_normalized = []
        text_arr = extract_sentences(token_list)
        for sent in text_arr:
            if not sent:
                continue
            pre, final = self.normalize(sent)
            pre_normalized.extend(pre)
            final_normalized.extend(final)

        pre_norm_linked = LinkedTokens()
        pre_norm_linked.init_from_prenorm_tuples(pre_normalized)
        norm_linked = LinkedTokens()
        norm_linked.init_from_norm_tuples(final_normalized)

        normalized_tokens = self.align_normalized(token_list, pre_norm_linked, norm_linked)

        return normalized_tokens

    def normalize(self, text: str) -> Tuple:
        """
        Normalize 'text' in two steps: first expand abbreviations and use that intermediate representation
        of 'text' as an input to the number normalizing step. Return results from both steps, organized in
        tuples with input and output of both steps, the number normalizing results also contain part-of-speech
        tag for each token.

        Example:
        text, input first step normalizing: 'Jón , f. 4. apríl 1927 , d. 10. maí 2010'
        returned prenorm_tuples: [('Jón', 'Jón'), (',', ','), ('f.', 'fæddur'), ('4.', '4.'), ('apríl', 'apríl'),
        ('1927', '1927'), (',', ','), ('d.', 'dáinn'), ('10.', '10.'), ('febrúar', 'febrúar'), ('2010', '2010')]
        input for second step normalizing:
        'Jón , fæddur 4. apríl 1927 , dáinn 10. maí 2020'
        returned normalized tuples: [('Jón', 'Jón', 'nken-s'), (',', ',', 'pk'), ('fæddur', 'fæddur', 'sþgken'),
        ('4.', ' fjórða', 'ta'), ('apríl', 'apríl', 'nkeo'), ('1927', ' nítján hundruð tuttugu og sjö', 'ta'),
        (',', ',', 'pk'), ('dáinn', 'dáinn', 'lkensf'), ('10.', ' tíunda', 'ta'), ('febrúar', 'febrúar', 'nkeo'),
        ('2010', ' tvö þúsund og tíu', 'ta')]

        :param text: the text to normalize
        :return: two lists of tuples, from both normalizing steps
        """
        abbr_sent = abbr_functions.replace_abbreviations(text, "other")
        prenorm_tuples = self.extract_prenorm_tuples(abbr_sent, text)
        expanded_abbr = ' '.join(abbr_sent)
        normalized = number_functions.handle_sentence(expanded_abbr.strip(), "other")

        return prenorm_tuples, normalized

    def extract_prenorm_tuples(self, prenorm_arr, sent):
        """
        Find changes in prenorm_sent compared to sent and create tuples with original token and expanded abbreviation.
        Example:
        sent == Það voru t.d. 5 atriði
        prenorm_sent == Það voru til dæmis 5 atriði

        return [('Það', 'Það'), ('voru', 'voru'), ('t.d.', 'til dæmis'), ('5', '5), ('atriði', 'atriði')]
        :param prenorm_arr: the output from the pre-normalizer processing 'sent'
        :param sent: the original sentence, the input for the pre-normalizer
        :return: A list of tuples containing original token and expanded version from the pre-normalizer
        """
        norm_tuples = []
        sent_arr = sent.split()

        diff = difflib.ndiff(sent_arr, prenorm_arr)
        # a token from sent_arr not occurring in the prenorm_arr,
        # store while processing the same/near positions in prenorm_arr
        current_keys = []
        # a token from prenorm_arr not occurring in the sent_arr,
        # store while processing the same/near positions in sent_arr
        current_values = []

        for elem in diff:
            if elem[0] == ' ':
                if current_keys and current_values:
                    # add the orignal (key) - prenorm (value) tuple to the results
                    norm_tuples.extend(self.extract_tuples(current_keys, current_values))
                    current_keys = []
                    current_values = []
                norm_tuples.append((elem[2:].strip(), elem[2:].strip()))
            elif elem[0] == '-':
                # elem in list1 but not in list2
                current_keys.append(str(elem[2:]))
            elif elem[0] == '+':
                # elem in list2 but not in list1
                current_values.append(str(elem[2:]))
        if current_keys and current_values:
            norm_tuples.extend(self.extract_tuples(current_keys, current_values))

        return norm_tuples

    def extract_tuples(self, keys, values):
        """Extract tuples from keys and values. Most of the time we will only have one element in the
        keys-array, and will then simply put a joined string from the values array as the second tuple
        element, regardless of the size of the values array. If the keys array contains more than one
        element, we first check if both arrays are equally long and we thus have a one on one mapping,
        if not, we have to use some heuristics to attach the prenormalized values to the original keys,
        namely to check if the first letters of keys/values match, indicating an expanded abbreviation."""
        tup_list = []
        if len(keys) == 1:
            tup_list.append((keys[0].strip(), ' '.join(values).strip()))
        elif len(keys) == len(values):
            zipped = zip(keys, values)
            for elem in zipped:
                tup_list.append((elem[0].strip(), elem[1].strip()))
        else:
            value_ind = 0
            current_val = values[value_ind]
            for elem in keys:
                matching = True
                val = ''
                elem_rest = elem
                while matching:
                    if elem_rest[0] == current_val[0]:
                        val += ' ' + current_val
                        value_ind += 1
                        if value_ind < len(values):
                            current_val = values[value_ind]
                        else:
                            break
                        elem_rest = elem_rest[1:]
                    elif elem_rest.startswith('.'):
                        # the dot will have been deleted if the prenorm expanded an abbreviation
                        # so check for a match of the next char
                        elem_rest = elem_rest[1:]
                    else:
                        matching = False
                tup_list.append((elem.strip(), val.strip()))

        return tup_list

    def align_normalized(self, token_list, pre_normalized, final_normalized):
        """Use all three input lists to enrich the tokens in token_list with normalized representations
        of the original tokens. Return a new list containing the same tokens as in token_list, enriched
        with normalized elements, and possibly added TagTokens, if created from normalized results.
        The intermediate pre_normalized list is needed, because the processed tokens from that list are the
        input for the normalizer, and thus necessary in the align step to compare tokens.

        :param token_list: the original token list, enriched with tokenized field
        :param pre_normalized: a linked list of pre-normalized nodes (abbreviations expanded)
        :param final_normalized: a linked list of normalized nodes (final results from the normalizer)
        :return a list of the tokens in token_list, enriched by normalized elements
        """
        normalized_tokens = []
        token_list_index = 0
        current_prenorm = pre_normalized.head
        current_norm = final_normalized.head
        # iterate through the original tokens
        while token_list_index < len(token_list):
            tok = token_list[token_list_index]
            if isinstance(tok, TagToken):
                normalized_tokens.append(tok)
                token_list_index += 1
                continue
            else:
                tokenized_token = ' '.join(tok.tokenized)
                if not tokenized_token:
                    # The original token might have been deleted during the cleaning step, so no
                    # further processing will have taken place. We keep the original token in the list for the record
                    normalized_tokens.append(tok)
                    # don't increment normalized lists in this case, they will not have a corresponding entry
                    token_list_index += 1
                    continue

                # The original (tokenized) token is the same as the input for the final normalizing step,
                # but the normalized version contains more than one token:
                # ['2010'] vs. (2021, tvö þúsund tuttugu og eitt, ta)
                elif tokenized_token == current_norm.token and len(current_norm.processed.split()) > 1:
                    normalized_arr = []
                    for word in current_norm.processed.split():
                        normalized_arr = self.extend_norm_arr(current_norm, normalized_arr, word)
                    tok.set_normalized(normalized_arr)
                    normalized_tokens.append(tok)
                    current_norm.visited = True

                # Same as last step, but the normalized version is only one token as well
                # ['10'] vs. (10, tíu, ta)
                # OR:
                # Was there a change during pre-normalization? Compare the original token with the prenorm input
                # and the prenorm output with the normalized input
                # ['-'] vs. (-,til) and (-,til) vs. (til, til)
                # This check also holds for elements that do not change through normalization, we have the same
                # original token as the input to the normalizer and can add the normalized version regardless
                # if it has changed the token or not
                elif tokenized_token == current_norm.token or (
                        tokenized_token == current_prenorm.token and current_prenorm.processed == current_norm.token):
                    word = current_norm.processed.strip()
                    normalized_arr = self.extend_norm_arr(current_norm, [], word)
                    tok.set_normalized(normalized_arr)
                    normalized_tokens.append(tok)
                    current_norm.visited = True

                # Did the pre normalization step expand an abbreviation to more tokens? This means that the input
                # for the final normalizing has more tokens than the original (for the example: 3 instead of 1)
                # Iterate through the tokens in the prenorm-results and the corresponding elements in the normalized list.
                # ['m/s'] vs. (m/s, metrar á sekúndu)
                elif tokenized_token == current_prenorm.token and len(current_prenorm.processed.split()) > 1:
                    normalized_arr = []
                    for j, word in enumerate(current_prenorm.processed.split()):
                        if current_norm.token == word:
                            norm_word = current_norm.processed
                            normalized_arr = self.extend_norm_arr(current_norm, normalized_arr, norm_word)
                            if current_norm.next:
                                current_norm.visited = True
                                current_norm = current_norm.next
                        else:
                            break
                    tok.set_normalized(normalized_arr)
                    normalized_tokens.append(tok)

                # Did the tokenizer split up the original token, so the original token tokenized spans more than
                # one entry in pre_normalized list?
                # original token: '10-12', tokenized: ['10','-','12'], tokenized_token: '10 - 12'
                # prenorm: (10, 10), (-, til), (12, 12)
                elif tokenized_token.startswith(current_prenorm.token):
                    normalized_arr = []
                    original_arr = tokenized_token.split()
                    while original_arr:
                        if current_norm.visited:
                            break
                        # did the pre-norm process split up the token in tok.tokenized?
                        no_prenorm_tokens = len(current_prenorm.processed.split())
                        original_tok_rest = ''.join(original_arr)
                        original_arr = self.update_original_arr(current_prenorm, original_arr)
                        pre_norm_arr = current_prenorm.processed.split()
                        pre_norm_str = ''.join(pre_norm_arr)
                        if original_tok_rest.startswith(pre_norm_str) or current_prenorm.processed.startswith(current_norm.token):
                            for k in range(no_prenorm_tokens):
                                norm_word = current_norm.processed.strip()
                                current_norm.visited = True
                                normalized_arr = self.extend_norm_arr(current_norm, normalized_arr, norm_word)
                                if current_norm.next:
                                    current_norm = current_norm.next
                                else:
                                    break
                        else:
                            # We should not get here!
                            print('original_token: ' + tokenized_token)
                            print('prenormalized: ' + current_prenorm.processed)

                        if current_prenorm.next:
                            current_prenorm = current_prenorm.next
                        if current_norm.visited and current_norm.next:
                            current_norm = current_norm.next

                    tok.set_normalized(normalized_arr)
                    normalized_tokens.append(tok)
                    current_prenorm = current_prenorm.previous

            token_list_index += 1
            if current_prenorm.next:
                current_prenorm = current_prenorm.next
            if current_norm.next:
                if current_norm.visited:
                    current_norm = current_norm.next

        return normalized_tokens

    def update_original_arr(self, current_prenorm, original_arr):
        """Remove the elements occurring in the current_prenorm tokens from the original array to ensure
        we are not going ahead of the original token with the normalized elements. When the original_arr
        is empty, we stop the current process and move on to the next token."""
        increment_for_orig_arr = len(current_prenorm.token.split())
        if increment_for_orig_arr < len(original_arr):
            original_arr = original_arr[increment_for_orig_arr:]
        else:
            original_arr = []
        return original_arr

    def extend_norm_arr(self, normalized_node, normalized_arr, word):
        punct = ''
        # we should not get punctuated tokens back from the normalizer, however, this
        # can happen, so we deal with that here and separate the word from the punctuation
        if word.endswith(',') or word.endswith('.'):
            punct = word[-1]
            word = word[:-1]
        if word:
            # create a normalized entry with pos = TAG for tags
            # in this case, the tag occurs within a token, so we don't create a tag-token here
            if word.startswith('<'):
                normalized = Normalized(word, 'TAG')
            else:
                normalized = Normalized(word, normalized_node.pos)
            normalized_arr.append(normalized)
        if punct:
            # for IceParser the pos of a puncutation char is the punctuation char itself
            normalized = Normalized(punct, punct)
            normalized_arr.append(normalized)
        return normalized_arr
