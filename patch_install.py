import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# The original code uses the '$' helper: $('#installX').addEventListener(...)
# We want to make sure the 'X' button actually hides the element.
# I will find the event listener for #installX and replace it with a more robust version.

pattern = r"(\#installX\").addEventListener\(\"click\",\s*\(\)\s*=>\s*\{[^}]*\}\);"
replacement = 'document.getElementById("installX").addEventListener("click", () => { const el = document.getElementById("install"); el.hidden = true; el.style.display = "none"; try { localStorage.setItem("bd-noinstall","1"); } catch(e){} });'

# We need to handle the fact that it might be in the form of $('#installX')
content = re.sub(r"\$\(\"installX\"\)\.addEventListener\(\"click\",\s*\(\)\s*=>\s*\{[^}]*\}\);", replacement, content)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
