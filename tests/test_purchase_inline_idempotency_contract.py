from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_each_inline_purchase_line_gets_a_fresh_idempotency_key():
    source = (ROOT / 'templates/purchase/purchase_detail.html').read_text(encoding='utf-8')
    assert 'function newLineOperationKey()' in source
    assert "const payload=new FormData(lineForm);payload.set('_idempotency_key',newLineOperationKey())" in source
    submit_block = source.split('async function submitPurchaseLine()', 1)[1].split("search?.addEventListener('input'", 1)[0]
    assert 'body:payload' in submit_block
    assert 'body:new FormData(lineForm)' not in submit_block
