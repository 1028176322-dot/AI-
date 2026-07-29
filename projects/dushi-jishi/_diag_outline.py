import sys, os
sys.path.insert(0, r'D:\AI-Workspace\platform\AI-Creative-Platform\scripts\project')
import outline_governance as og

ROOT = r'D:\AI-Workspace\projects\dushi-jishi'

# 1) planning-policy 关键字段
policy_path = os.path.join(ROOT, 'sources', 'outline', '_intake', 'planning-policy.yaml')
import importlib.util
spec = importlib.util.spec_from_file_location('_gov', r'D:\AI-Workspace\platform\AI-Creative-Platform\scripts\_common\_gov.py')
_gov = importlib.util.module_from_spec(spec); spec.loader.exec_module(_gov)
policy = (_gov.load_yaml(policy_path) or {}).get('planning_policy') or {}
print('=== planning-policy key fields ===')
for k in ['project_id','total_chapters', 'total_chapters_floor', 'binding', 'detailed_window', 'all_chapters_detailed_required', 'minimum_future_detailed_plans']:
    print('  %s = %r' % (k, policy.get(k)))

# 2) 直接跑 validate_project (require_approved=False, 与 gap matrix 一致)
print('=== validate_project(require_approved=False) ===')
rep = og.validate_project(ROOT, write=False, require_approved=False)
ov = rep.get('outline_validation', {})
print('  gate decision:', ov.get('gate', {}).get('decision'))
all_errs = ov.get('gate', {}).get('reasons', [])
print('  total errors:', len(all_errs))
# 分类统计
from collections import Counter
cat = Counter()
for e in all_errs:
    if 'previous_plan_id' in e: cat['prev_link'] += 1
    elif 'next_plan_id' in e: cat['next_link'] += 1
    elif 'mismatches chapter map' in e: cat['map_mismatch'] += 1
    elif 'anti-template' in e: cat['anti_template'] += 1
    elif 'missing' in e: cat['missing'] += 1
    else: cat['other'] += 1
print('  categories:', dict(cat))
print('  first 20 errors:')
for e in all_errs[:20]:
    print('   -', e)
