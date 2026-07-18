import difflib
print(difflib.SequenceMatcher(None, "upasni", "ms. s. a. upasani").ratio())
print(difflib.SequenceMatcher(None, "upasni", "upasani").ratio())
