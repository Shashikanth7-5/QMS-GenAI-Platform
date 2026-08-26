path = r"C:\Users\2141673\OneDrive - Cognizant\Documents\GEN AI\QMS Project\routes\capa.py"
with open(path, encoding="utf-8") as f:
    lines = f.readlines()
cutoff = None
for i, line in enumerate(lines):
    if "_smart_mock(record, question)" in line:
        cutoff = i + 1
if cutoff:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines[:cutoff])
    print(f"Done — kept {cutoff} lines")
else:
    print("Marker not found")
