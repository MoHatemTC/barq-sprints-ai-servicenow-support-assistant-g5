from Services.text_cleaner import clean_html_text


html = """
<p> </p>
<h1>Application Won&#39;t Launch or Install</h1>
<p>· Confirm the software is compatible with the current OS and hardware</p>
<p>· Verify the installer comes from a trusted source</p>
"""

clean_text = clean_html_text(html)

print("========== CLEAN TEXT ==========")
print(clean_text)
print("================================")

