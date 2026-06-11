import os

files = [
    r"routes\rag_extract.py",
    r"services\ai_service.py",
    r"services\ingestion_service.py",
    r"services\chains\inquiry_chain.py",
]

base = r"C:\Users\2141673\OneDrive - Cognizant\Documents\GEN AI\QMS Project"

ssl_line = '_SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() == "true"\n'

for rel in files:
    path = os.path.join(base, rel)
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if any("_SSL_VERIFY" in l for l in lines):
        print("ALREADY DONE:", rel)
        continue
    last_import = 0
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            last_import = i
    lines.insert(last_import + 1, ssl_line)
    lines = [l.replace("verify=False", "verify=_SSL_VERIFY").replace("verify = False", "verify=_SSL_VERIFY") for l in lines]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("FIXED:", rel)
