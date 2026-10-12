def rd(p):
    return open(p, encoding='utf-8', newline='').read().replace('\r\n', '\n')
def wr(p, s):
    open(p, 'w', encoding='utf-8', newline='').write(s.replace('\n', '\r\n'))
def sub(s, a, b, n=1):
    assert s.count(a) == n, (s.count(a), a[:80])
    return s.replace(a, b)
