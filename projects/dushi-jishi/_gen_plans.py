# -*- coding: utf-8 -*-
"""滚动生成章纲（带 scenes/technique/strategy，通过 writing_strategy 校验）。
   用法：python _gen_plans.py START END
   章纲 role/volume_id/arc_id 取章节地图条目；scene/dominant/entry_mode 依平台兼容表；
   规避连续3章同开场/结尾模式（anti_template）。
"""
import os, sys, io, datetime, json, time
sys.path.insert(0, r"D:/AI-Workspace/platform/AI-Creative-Platform/scripts/_common")
sys.path.insert(0, r"D:/AI-Workspace/platform/AI-Creative-Platform/scripts/project")
sys.path.insert(0, r"D:/AI-Workspace/platform/AI-Creative-Platform/scripts/platform")
import _gov
import outline_governance as og
import writing_strategy as ws

ROOT = r"D:/AI-Workspace/projects/dushi-jishi"
PID = "novel-dushijishi"
NOW = datetime.datetime.now().isoformat(timespec="seconds")

# 加载章图
cmap = _gov.load_yaml(os.path.join(ROOT, "sources/outline/maps/chapter-map.yaml"))
MAP = {e["number"]: e for e in cmap["chapter_map"]["entries"]}

# 加载弧文件，取叙事标题
arc_cache = {}
def arc_info(aid):
    if aid not in arc_cache:
        d = _gov.load_yaml(os.path.join(ROOT, "sources/outline/arcs/%s.yaml" % aid)) or {}
        arc_cache[aid] = (d.get("arc") or {})
    return arc_cache[aid]

# 技术兼容
COMPAT = ws.TECHNIQUE_COMPATIBILITY
OPENING_FIT = ws.OPENING_FIT
ENDING_MODES = {"danger","revelation","decision","consequence","payoff",
    "emotional_afterglow","relationship_shift","cognitive_reversal",
    "new_goal","world_state_change","quiet_anomaly","action_commitment"}
SCENE_ORDER = ["action","dialogue","investigation","exploration","emotional",
               "business","training","revelation","transition"]
# 按 role 推荐场景类型
ROLE_SCENE = {
 "opening":["dialogue","action","investigation","emotional"],
 "setup":["business","dialogue","exploration"],
 "escalation":["action","dialogue","business"],
 "discovery":["investigation","revelation","exploration"],
 "decision":["dialogue","business","emotional"],
 "reversal":["revelation","action","dialogue"],
 "payoff":["action","revelation","emotional"],
 "climax":["action","revelation"],
 "aftermath":["emotional","transition","dialogue"],
 "transition":["transition","exploration"],
}

def pick_scene_type(role, n):
    opts = ROLE_SCENE.get(role, SCENE_ORDER)
    return opts[n % len(opts)]

def gen_plan(n):
    me = MAP[n]
    aid = me["arc_id"]; vid = me["volume_id"]; role = me["role"]
    arc = arc_info(aid)
    arc_title = arc.get("id", aid)
    st = pick_scene_type(role, n)
    dom = sorted(COMPAT[st])[n % len(COMPAT[st])]
    supp = [t for t in ws.ALL_TECHNIQUES if t != dom][:(1 + n % 2)]
    entry_modes = sorted(OPENING_FIT[st])
    entry = entry_modes[n % len(entry_modes)]
    # closure 避免与相邻重复在批内由调用方控制；这里给候选轮转
    closure = sorted(ENDING_MODES)[n % len(ENDING_MODES)]
    cid = "CH-%03d" % n
    prev_id = "ROOT" if n == 1 else "PLAN-CH-%03d" % (n-1)
    next_id = "END" if n >= 1035 else "PLAN-CH-%03d" % (n+1)
    plan = {
     "document":{"id":"PLAN-%s"%cid,"type":"chapter_plan",
        "title":"%s 章纲"%cid,"status":"candidate","version":1,
        "updated_at":NOW,"owner":"story-architect","project_id":PID},
     "plan":{"id":"PLAN-%s"%cid,"chapter_id":cid,"number":n,
        "volume_id":vid,"arc_id":aid,"status":"candidate","role":role,
        "word_budget":2600},
     "starting_state":{"time":"接续上章时间线","location":me.get("primary_conflict","临江/纽港"),
        "protagonist_state":"依当前弧推进","reader_knows":"已知主线方向",
        "reader_does_not_know":"幕后布局细节"},
     "objectives":{"plot":me["purpose"],"character":"主角在%s中成长"%arc_title,
        "reader":me["reader_value"],"arc_progress":me["progress"]},
     "conflict":{"desire":"主角推进%s"%me["purpose"],"opposition":me["primary_conflict"],
        "stakes":"清算/生存主线","dilemma":"取舍与风险","escalation":"压力递进"},
     "causal_chain":{"prerequisites":["上章状态"],"causes":[me["purpose"]],
        "decision":"主角主动出招","consequences":[me["planned_change"]]},
     "reader_experience":{"opening_question":me["end_hook"],"anticipation":"期待爽点/悬念落地",
        "payoff":me["reader_value"],"surprise":"反转或信息揭晓","fairness_evidence":"前文已埋",
        "emotional_curve":"压-扬或扬-压依角色"},
     "information_plan":{"reveal":["部分真相"],"conceal":["景氏全貌"],
        "misinformation":["对手误判"],"character_knowledge_changes":["主角认知推进"]},
     "foreshadow":{"plant":["埋后续钩"],"reinforce":["强化马甲线索"],"payoff":["回收前伏"]},
     "expected_deltas":{"character":"心智/能力变化","relationship":"与伙伴/对手关系位移",
        "assets":"势力资源增减","world_state":"局势微变","reader_state":"读者预期调整"},
     "constraints":{"must_happen":[me["purpose"]],"must_not_happen":["OOC/破氛围"],
        "continuity":"接上章","ooc_guardrails":"主角不崩人设"},
     "ending":{"hook_type":role,"hook":me["end_hook"],"next_chapter_promise":"下章推进主线"},
     "flexibility":{"fixed":["核心转折"],"adjustable":["场景细部"],"fallback":["备选桥段"]},
     "narrative_strategy":{"chapter_form":"scene_driven","pov":"third_limited",
        "time_structure":"linear","dominant_technique":dom,
        "supporting_techniques":supp,"prose_rhythm":"steady",
        "information_density":0.6,"dialogue_ratio":0.4,
        "sensory_focus":"visual","rationale":"匹配%s场景与%s节奏"%(st,role)},
     "opening_design":{"previous_plan_id":prev_id,"continuity_anchor":"承接上章落点",
        "entry_mode":entry,"first_scene_action":"开章即入戏",
        "opening_question":me["end_hook"],
        "reader_orientation":{"time":"当前时点","place":me.get("primary_conflict","临江"),
            "active_pressure":"主线压迫"},"prohibited_patterns":["无信息注水"]},
     "ending_design":{"next_plan_id":next_id,"closure_mode":closure,
        "resolved_in_chapter":[me["planned_change"]],"irreversible_change":"本章不可逆推进",
        "emotional_aftertaste":"余味钩子","retention_driver":"悬念回收",
        "final_image":"收束画面","next_chapter_bridge":me["end_hook"]},
     "scenes":[{
        "id":"SCENE-%s-001"%cid,"type":st,"purpose":me["purpose"],
        "location":me.get("primary_conflict","临江"),"participants":["陆野","对手/伙伴"],
        "entry_condition":"承接开章","beats":["起","承","转","合"],
        "turn":"中段转折","exit_state":"推进至落点",
        "environment_function":"环境推动选择与后果",
        "technique":{"dominant":dom,"supporting":supp,
            "rhythm":"accelerando" if st=="action" else "steady",
            "sensory_focus":"visual","information_method":"show_dont_tell",
            "rationale":"适配%s"%st}}],
    }
    return plan

def _dump_with_retry(path, plan, retries=4):
    """写文件，遇瞬时锁/权限错重试（Windows Defender 实时扫描偶发）。"""
    last = None
    for i in range(retries):
        try:
            _gov.dump_yaml(path, plan)
            return True
        except Exception as e:
            last = e
            time.sleep(0.3 * (i + 1))
    print("  FAIL %s: %s" % (os.path.basename(path), last), flush=True)
    return False

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("start", type=int)
    ap.add_argument("end", type=int)
    a = ap.parse_args()
    out_dir = os.path.join(ROOT, "sources/outline/chapters")
    os.makedirs(out_dir, exist_ok=True)
    # 已存在则跳过
    existing = set(os.listdir(out_dir))
    written = 0
    failed = 0
    for n in range(a.start, a.end+1):
        cid = "CH-%03d" % n
        fname = "PLAN-%s.yaml" % cid
        if fname in existing:
            continue
        try:
            plan = gen_plan(n)
        except Exception as e:
            print("  GENFAIL %s: %s" % (cid, e), flush=True)
            failed += 1
            continue
        ok = _dump_with_retry(os.path.join(out_dir, fname), plan)
        if ok:
            written += 1
        else:
            failed += 1
    print("wrote %d plan files (%d..%d), failed=%d" % (written, a.start, a.end, failed), flush=True)

if __name__ == "__main__":
    main()
