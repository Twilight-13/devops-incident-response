import sys
import re

with open("ui_test.py", "r", encoding="utf-8") as f:
    ui_html = f.read()

# Remove the first line (`html_content = """`) and the last line (`"""`)
ui_html = ui_html.replace('html_content = """', '')
ui_html = ui_html[:-3] # remove last """

# Escape curly braces
ui_html = ui_html.replace('{', '{{').replace('}', '}}')

with open("server/app.py", "r", encoding="utf-8") as f:
    app_content = f.read()

# The function to replace is def dashboard() ... to </html>"""
# Let's find def dashboard():
start_idx = app_content.find("def dashboard():")
end_idx = app_content.find("</html>\"\"\"", start_idx) + len("</html>\"\"\"")

if start_idx == -1 or end_idx == -1:
    print("Could not find dashboard function in server/app.py")
    sys.exit(1)

new_dashboard = f'''def dashboard():
    html = f"""{ui_html}"""
    return html'''

new_content = app_content[:start_idx] + new_dashboard + app_content[end_idx:]

with open("server/app.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("Successfully replaced dashboard endpoint!")
