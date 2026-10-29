#!/usr/bin/env python3
"""Find the numbers someone says in a video and turn them into a plan of animated graphs.

usage: python autostats.py input.words.json      -> prints what it found and the plan (JSON)
fx.py --auto-stats calls detect() itself; this file never needs to be run by hand.

What it recognises (from the transcript made by words.py):
  "from 50,000 to 100,000 followers"        -> liquid-glass-graph (a climbing graph, the number counts up)
  "2,000 Jews, 1,000 Muslims, 4,000 ..."    -> bar-chart (one labelled bar per number, each when it is said)
  "40%" / "forty percent"                   -> percent-ring
Numbers can come as digits ("2", ",000", "%"), as "2,000", as "1.5 million" or in words ("two hundred hours").
A percentage that contradicts the figures said just before it (e.g. 40% for something that is 1,000 out of 7,000)
is NOT drawn: it is reported instead, because a wrong graph on screen is worse than none.
"""
import json, re, sys

ONES = {w: i for i, w in enumerate('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen '
                                   'seventeen eighteen nineteen'.split())}
TENS = {w: 10 * (i + 2) for i, w in enumerate('twenty thirty forty fifty sixty seventy eighty ninety'.split())}
SCALES = {'hundred': 100, 'thousand': 1e3, 'million': 1e6, 'billion': 1e9}
SUFFIX = {'k': 1e3, 'thousand': 1e3, 'm': 1e6, 'million': 1e6, 'b': 1e9, 'billion': 1e9}
STOP = {'and', 'the', 'a', 'an', 'of', 'which', 'that', 'in', 'on', 'at', 'to', 'for', 'with', 'is', 'are', 'was', 'were', 'it', 'its', 'my', 'our',
        'like', 'about', 'around', 'than', 'so', 'but', 'or', 'by', 'from', 'then', 'also', 'just', 'only', 'makes', 'make', 'represents'}


def norm(w): return re.sub(r"^[^\w%,.]+|[^\w%]+$", '', w.strip().lower())


def parse_numbers(words):
    """-> list of {i, j, s, e, value, pct}: a number made of words i..j (inclusive)."""
    toks = [norm(w['w']) for w in words]; out = []; i = 0
    def hy(x):  # 'ninety-seven' -> 97, or None
        p_ = x.split('-')
        return sum(ONES.get(q, TENS.get(q, 0)) for q in p_) if len(p_) > 1 and all(q in ONES or q in TENS for q in p_) else None
    while i < len(words):
        t = toks[i]; j = i; val = None; pct = False
        m = re.fullmatch(r'(\d+(?:\.\d+)?)(k|m|b|%)?', t.replace(',', '')) if re.fullmatch(r'[\d,.]+(k|m|b|%)?', t) else None
        if m:  # digits, maybe glued to a suffix, maybe followed by ",000" style tokens
            val = float(m.group(1)); suf = m.group(2)
            if suf == '%': pct = True
            elif suf: val *= SUFFIX[suf]
            while j + 1 < len(words) and re.fullmatch(r',\d{3}', toks[j + 1]) and not suf: val = val * 1000 + float(toks[j + 1][1:]); j += 1
            if not suf and j + 1 < len(words):
                n = toks[j + 1]
                if n in ('%', 'percent', 'per'): pct = True; j += 1 + (n == 'per' and j + 2 < len(words) and toks[j + 2] == 'cent')
                elif n in SUFFIX: val *= SUFFIX[n]; j += 1
        elif t in ONES or t in TENS or t in SCALES or hy(t) is not None:  # number words: "two hundred and fifty thousand"
            total = cur = 0; k = i; seen = False
            while k < len(words):
                x = toks[k]
                if hy(x) is not None: cur += hy(x)
                elif x in ONES: cur += ONES[x]
                elif x in TENS: cur += TENS[x]
                elif x == 'hundred': cur = max(cur, 1) * 100
                elif x in ('thousand', 'million', 'billion'): total += max(cur, 1) * SCALES[x]; cur = 0
                elif x == 'and' and k + 1 < len(words) and (toks[k + 1] in ONES or toks[k + 1] in TENS or hy(toks[k + 1]) is not None) and seen: k += 1; continue
                else: break
                seen = True; k += 1
            if not seen or (t == 'and'): i += 1; continue
            val = total + cur; j = k - 1
            if j + 1 < len(words) and toks[j + 1] in ('%', 'percent'): pct = True; j += 1
        if val is None: i += 1; continue
        out.append({'i': i, 'j': j, 's': words[i]['s'], 'e': words[j]['e'], 'value': val, 'pct': pct}); i = j + 1
    return out


def label_after(words, j, n=2):
    """The noun(s) right after a number: '1,000 Muslims,' -> 'Muslims'."""
    got = []
    for k in range(j + 1, min(len(words), j + 1 + 3)):
        w = norm(words[k]['w'])
        if not w or w in STOP or re.fullmatch(r'[\d,.%]+', w):
            if got: break
            continue
        got.append(re.sub(r'[^\w]', '', words[k]['w']).capitalize())
        if len(got) >= n or re.search(r'[,.;:!?]$', words[k]['w'].strip()): break
    return ' '.join(got)


def short(v):
    """100000 -> '100K', 1500000 -> '1.5M', 40 -> '40'."""
    for div, suf in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if abs(v) >= div: return f'{v / div:g}{suf}'
    return f'{v:g}'


def detect(words, min_gap=1.0, keep_inconsistent=False):
    """-> (plan, notes): plan is a list of effects for fx.py, notes are plain-language lines for the person."""
    nums = parse_numbers(words); plan, notes, used = [], [], set()
    toks = [norm(w['w']) for w in words]
    # 1. "from A to B" -> a climbing graph
    for a, b in zip(nums, nums[1:]):
        if a['pct'] or b['pct'] or a['i'] in used: continue
        between = toks[a['j'] + 1:b['i']]
        if a['i'] > 0 and toks[a['i'] - 1] == 'from' and between in (['to'], ['up', 'to'], ['till'], ['until']):
            lab = label_after(words, b['j'], 1) or 'Growth'
            plan.append({'fx': 'liquid-glass-graph', 'start': max(0, a['s'] - 0.3), 'end': b['e'] + 2.2, 'text': lab, 'from': short(a['value']), 'to': short(b['value'])})
            used |= {a['i'], b['i']}; notes.append(f"{lab}: {short(a['value'])} to {short(b['value'])} at {a['s']:.1f}s (climbing graph)")
    # 2. labelled figures said one after another -> bars
    items = []
    for n in nums:
        if n['i'] in used or n['pct']: continue
        lab = label_after(words, n['j'], 1)
        if lab: items.append({**n, 'label': lab})
    groups, cur = [], []
    for it in items:
        if cur and it['s'] - cur[-1]['e'] > 6.0: groups.append(cur); cur = []
        cur.append(it)
    if cur: groups.append(cur)
    bars = []
    for g in groups:
        if len(g) < 2:
            notes.append(f"{g[0]['label']}: {short(g[0]['value'])} at {g[0]['s']:.1f}s, a single figure, so no graph (nothing to compare it to)")
            continue
        g = g[:4]
        plan.append({'fx': 'bar-chart', 'start': max(0, g[0]['s'] - 0.2), 'end': g[-1]['e'] + 2.8, 'text': 'In numbers',
                     'bars': '|'.join(f"{x['label']}:{x['value']:g}@{x['s']:.2f}" for x in g)})
        bars.append(g); used |= {x['i'] for x in g}
        notes.append('Bars: ' + ', '.join(f"{x['label']} {x['value']:,.0f} ({x['s']:.1f}s)" for x in g))
    # 3. percentages -> a ring, unless they contradict the figures said just before
    for n in nums:
        if not n['pct'] or n['i'] in used: continue
        before = [norm(w['w']) for w in words[max(0, n['i'] - 9):n['i']]]
        lab = None; ok = True; best = None
        for g in bars:  # the closest figure label said just before the percentage is the one it is about
            total = sum(x['value'] for x in g)
            for x in g:
                stem = x['label'].lower().rstrip('s')
                for pos, b in enumerate(before):
                    if b.rstrip('s') == stem and (best is None or pos > best[0]): best = (pos, x, total)
        if best:
            _, x, total = best; lab = x['label']; share = 100 * x['value'] / total
            if abs(share - n['value']) > 5:
                ok = keep_inconsistent
                notes.append(f"WARNING: you say {n['value']:g}% for {x['label']} at {n['s']:.1f}s, but {x['value']:,.0f} out of {total:,.0f} is {share:.0f}%. "
                             + ('Drawn anyway.' if ok else 'Not drawn: tell me which one is right.'))
        if not lab:
            after = label_after(words, n['j'] + 2, 1) if n['j'] + 1 < len(words) and toks[n['j'] + 1] == 'of' else label_after(words, n['j'], 1)
            lab = after or 'Share'
        if ok:
            plan.append({'fx': 'percent-ring', 'start': max(0, n['s'] - 0.6), 'end': n['e'] + 2.6, 'text': lab, 'value': f"{n['value']:g}%"})
            notes.append(f"{lab}: {n['value']:g}% at {n['s']:.1f}s (ring)")
    # the cards all sit under the chin, so two must never be on screen together: cut the earlier one short
    plan.sort(key=lambda d: d['start'])
    for a, b in zip(plan, plan[1:]):
        if a['end'] > b['start'] - 0.1: a['end'] = max(a['start'] + min_gap, b['start'] - 0.1)
    return plan, notes


if __name__ == '__main__':
    words = json.load(open(sys.argv[1]))
    plan, notes = detect(words)
    print('\n'.join(notes) or 'No numbers found.'); print(json.dumps({'effects': plan}, indent=1))
