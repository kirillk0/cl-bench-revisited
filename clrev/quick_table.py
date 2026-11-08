"""Quick per-question cross-mode table: python -m clrev.quick_table <model> [run_glob]"""
import glob, json, os, sys

def main():
    model = sys.argv[1]
    pattern = sys.argv[2] if len(sys.argv) > 2 else f"runs/{model}_*"
    runs = {}
    for p in sorted(glob.glob(pattern)):
        sp = os.path.join(p, "summary.json")
        if os.path.isdir(p) and os.path.exists(sp):
            runs[os.path.basename(p)] = json.load(open(sp))
    qids = [q["id"] for q in json.load(open("data/questions_v2.json"))]
    cols = list(runs)
    short = [c.replace(model + "_", "") for c in cols]
    print(f"{'q':5} " + " | ".join(f"{s:<22}" for s in short))
    per = {c: {r["question_id"]: r for r in runs[c]["per_question"]} for c in cols}
    for q in qids:
        cells = []
        for c in cols:
            r = per[c].get(q)
            if not r:
                cells.append(f"{'-':<22}"); continue
            mark = "✓" if r.get("correct") else ("E" if r.get("error") else "✗")
            cells.append(f"{mark} sql={r.get('n_sql',0):>2} b={r.get('n_bash',0):>2} ${r.get('cost_usd',0):.4f}")
        print(f"{q:5} " + " | ".join(cells))
    print()
    for c in cols:
        s = runs[c]; t = s["totals"]
        print(f"{c:28} acc={s['accuracy']:.3f} pre={s['accuracy_pre_drift']} post={s['accuracy_post_drift']} cost=${t['cost_usd']:.4f} "
              f"in={t.get('input')} cached={t.get('cached')} out={t.get('output')} reasoning={t.get('reasoning')} sql={t.get('n_sql')} bash={t.get('n_bash')} wall={t.get('wall_s'):.0f}s")

if __name__ == "__main__":
    main()
