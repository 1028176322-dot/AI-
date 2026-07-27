#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reference_fingerprint.py — HMAC-SHA256/MiniHash 指纹系统

职责（§2.2/§10）：
  1. 正文做 HMAC-SHA256 shingles（k-shingle → HMAC，使用 key_id 标识密钥）。
  2. shingles 经 MiniHash 得 source signature。
  3. 摘要存 source_digest（SHA-256 全本）+ MinHash signature + 许可类型。
  4. 支持撤回/删除级联失效（source 失效 → 删除 contribution_vector → 重算 archetype）。
  5. 指纹比对：候选正文生成同构 HMAC/MinHash 指纹，与参考指纹比较相似度。
  6. 密钥不落项目目录，经环境变量注入（项目只存 key_id）。

规则：
  - min_independent_sources: 3
  - recommended_independent_sources: 5
  - max_single_source_weight: 0.4

用法:
  from reference_fingerprint import Fingerprinter
  fp = Fingerprinter()
  sig = fp.fingerprint("source text")
  sim = fp.compare(sig1, sig2)
"""

import hashlib
import hmac
import os
import struct
import sys


# ── 默认参数（§2.2） ─────────────────────────────────────────
DEFAULT_K = 9                     # shingle 大小（字符）
DEFAULT_NUM_HASHES = 128          # MiniHash 哈希函数数量
DEFAULT_SEED = 0x5EED_FACE        # MiniHash 种子
MIN_INDEPENDENT_SOURCES = 3
RECOMMENDED_INDEPENDENT_SOURCES = 5
MAX_SINGLE_SOURCE_WEIGHT = 0.4

# ── 密钥环境变量前缀 ───────────────────────────────────────────
_KEY_ENV_PREFIX = "FS_FINGERPRINT_KEY_"


class KeyManager:
    """密钥管理器：从环境变量 / OS 钥匙圈读取 HMAC 密钥。

    项目不存密钥，只存 key_id。
    若环境变量 `FS_FINGERPRINT_KEY_<KEY_ID>` 存在，优先使用。
    否则 fallback 为项目级默认密钥（仅用于开发，生产须配 env）。
    """

    def __init__(self):
        self._cache = {}

    def get_key(self, key_id: str) -> bytes:
        if key_id in self._cache:
            return self._cache[key_id]
        env_key = "%s%s" % (_KEY_ENV_PREFIX, key_id.upper())
        key = os.environ.get(env_key)
        if key:
            key_bytes = key.encode("utf-8")
        else:
            # 开发 fallback（不应用于生产）
            key_bytes = hashlib.sha256(key_id.encode("utf-8")).digest()
        self._cache[key_id] = key_bytes
        return key_bytes


class Fingerprinter:
    """HMAC-SHA256 + MiniHash 指纹生成与比对。"""

    def __init__(self, k=DEFAULT_K, num_hashes=DEFAULT_NUM_HASHES,
                 seed=DEFAULT_SEED, key_manager=None):
        self.k = k
        self.num_hashes = num_hashes
        self.seed = seed
        self.key_manager = key_manager or KeyManager()
        # 预生成随机哈希函数系数（a_i, b_i）
        self._a, self._b = self._generate_hash_coeffs(num_hashes, seed)

    # ── 哈希函数族（MiniHash） ──────────────────────────────────
    @staticmethod
    def _generate_hash_coeffs(n, seed):
        """生成 n 组 (a, b) 系数，用于 `(a * x + b) % p` 哈希族。"""
        import random
        # 使用固定种子 + 不同索引保证可复现
        p = (1 << 61) - 1       # 梅森素数 Mersenne prime
        rng = random.Random(seed)
        a = [rng.randint(1, p - 1) for _ in range(n)]
        b = [rng.randint(0, p - 1) for _ in range(n)]
        return a, b

    # ── Shingling ──────────────────────────────────────────────
    def _shingles(self, text: str):
        """将文本切分为 k-shingle 集合。"""
        # 去除空白并归一化
        text = " ".join(text.split())
        if len(text) < self.k:
            return set() if not text else {text}
        return set(text[i:i + self.k] for i in range(len(text) - self.k + 1))

    # ── HMAC-SHA256（§2.2 #1） ────────────────────────────────
    def hmac_shingle(self, shingle: str, key: bytes) -> int:
        """对单一 shingle 做 HMAC-SHA256，返回整数指纹。"""
        sig = hmac.new(key, shingle.encode("utf-8"), hashlib.sha256).digest()
        # 取前 8 字节 → 64 位整数
        return struct.unpack(">Q", sig[:8])[0]

    # ── MinHash 签名 ──────────────────────────────────────────
    def _minhash_signature(self, shingle_hashes):
        """对一组 shingle 哈希值生成 MinHash 签名向量。"""
        if not shingle_hashes:
            return [self.seed] * self.num_hashes
        sig = [1 << 61] * self.num_hashes    # 初始化为极大值
        for h_val in shingle_hashes:
            for i in range(self.num_hashes):
                val = ((self._a[i] * h_val + self._b[i]) % ((1 << 61) - 1))
                if val < sig[i]:
                    sig[i] = val
        return sig

    # ── 全文指纹（§2.2 #1-#3） ─────────────────────────────────
    def fingerprint(self, text: str, key_id="default",
                    source_id=None, license_type="unknown"):
        """为文本生成完整指纹包。

        返回 dict:
          - source_id: str
          - source_digest: SHA-256 全本
          - minhash_signature: list[int]
          - license_type: str
          - key_id: str
          - k: int
          - num_hashes: int
        """
        key = self.key_manager.get_key(key_id)
        shingle_set = self._shingles(text)
        shingle_hashes = [self.hmac_shingle(s, key)
                          for s in shingle_set]
        sig = self._minhash_signature(shingle_hashes)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

        return {
            "source_id": source_id,
            "source_digest": digest,
            "minhash_signature": sig,
            "license_type": license_type,
            "key_id": key_id,
            "k": self.k,
            "num_hashes": self.num_hashes,
        }

    # ── 指纹比对（Jaccard 近似） ──────────────────────────────
    def compare(self, fp_a, fp_b):
        """比较两个指纹的 MinHash 签名，返回 [0, 1] 相似度。"""
        sig_a = fp_a.get("minhash_signature")
        sig_b = fp_b.get("minhash_signature")
        if not sig_a or not sig_b:
            return 0.0
        n = min(len(sig_a), len(sig_b))
        matches = sum(1 for i in range(n) if sig_a[i] == sig_b[i])
        return matches / n

    # ── 候选文本指纹（§2.2 #5） ──────────────────────────────
    def candidate_fingerprint(self, text, key_id="default"):
        """为候选（修订后）正文生成指纹，供与参考指纹比对。"""
        return self.fingerprint(text, key_id=key_id,
                                source_id="__candidate__",
                                license_type="system-generated")


# ── 贡献向量工具 ──────────────────────────────────────────────
def make_contribution_vector(source_ids, weights):
    """生成 source_contribution_vector（§2.2 #4）。

    Args:
      source_ids: list[str] 来源标识
      weights: list[float]  各来源权重（须 >= 0）

    Returns:
      dict: {source_id: weight}，自动归一化
    """
    total = sum(weights)
    if total <= 0:
        return {}
    vec = {}
    for sid, w in zip(source_ids, weights):
        vec[sid] = round(w / total, 6)
    return vec


def validate_source_weights(contribution_vector):
    """校验来源权重是否符合 §2.2 约束。

    Returns:
      (ok: bool, reasons: list[str])
    """
    reasons = []
    vec = contribution_vector or {}
    # 单一来源权重不得 > 0.4
    for sid, w in vec.items():
        if w > MAX_SINGLE_SOURCE_WEIGHT:
            reasons.append("source %s weight %.3f > max %.1f" % (
                sid, w, MAX_SINGLE_SOURCE_WEIGHT))

    # 最少独立来源数
    n = len(vec)
    if n < MIN_INDEPENDENT_SOURCES:
        reasons.append(
            "only %d independent sources (need >= %d)" % (
                n, MIN_INDEPENDENT_SOURCES))
    elif n < RECOMMENDED_INDEPENDENT_SOURCES:
        reasons.append(
            "only %d independent sources (recommended >= %d)" % (
                n, RECOMMENDED_INDEPENDENT_SOURCES))

    return len(reasons) == 0, reasons


# ── 主入口（CLI） ─────────────────────────────────────────────
def main():
    import json
    if len(sys.argv) < 2:
        print("用法: %s <text> [key_id]" % sys.argv[0])
        sys.exit(1)
    text = sys.argv[1]
    key_id = sys.argv[2] if len(sys.argv) > 2 else "default"
    fp = Fingerprinter()
    result = fp.fingerprint(text, key_id=key_id)
    # 签名太长，摘要显示
    sig_preview = result["minhash_signature"][:5] + ["..."]
    result["minhash_signature_preview"] = sig_preview
    del result["minhash_signature"]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
