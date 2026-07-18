import difflib
print(difflib.get_close_matches("Upasni Mam", ["Ms. S. A. Upasani", "Dr. K. S. Dhabekar"], n=1, cutoff=0.5))
print(difflib.get_close_matches("upasni", ["ms. s. a. upasani", "dr. k. s. dhabekar"], n=1, cutoff=0.5))
