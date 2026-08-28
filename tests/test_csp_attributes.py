from services.csp import inline_attribute_directives


def test_inline_attributes_use_exact_hashes_not_unsafe_inline():
    html = '''<html><body>
      <button style="color:red" onclick="window.print()">Print</button>
      <form onsubmit="return confirm('ok')"></form>
    </body></html>'''
    style, script = inline_attribute_directives(html)
    assert style.startswith("style-src-attr 'unsafe-hashes' 'sha256-")
    assert script.startswith("script-src-attr 'unsafe-hashes' 'sha256-")
    assert "'unsafe-inline'" not in style
    assert "'unsafe-inline'" not in script
    assert style.count("'sha256-") == 1
    assert script.count("'sha256-") == 2


def test_inline_attribute_policy_fails_closed_when_absent():
    style, script = inline_attribute_directives('<p>Safe</p>')
    assert style == "style-src-attr 'none'"
    assert script == "script-src-attr 'none'"


def test_character_references_hash_as_decoded_dom_values():
    plain = inline_attribute_directives('<button onclick="a && b()">x</button>')[1]
    encoded = inline_attribute_directives('<button onclick="a &amp;&amp; b()">x</button>')[1]
    assert plain == encoded
