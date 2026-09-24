from decimal import Decimal, InvalidOperation


def weigh(aroma: float, taste: float, liquor: float) -> tuple[str, str, float]:
    score = round(aroma * 0.3 + taste * 0.5 + liquor * 0.2, 2)
    if score >= 7:
        return "通过", "加权分达到放行线", score
    return "不通过", "加权分低于放行线", score


def check_scale(pairs: list[tuple[str, str]]):
    """校验一批 (母叶名, 占比) 行。

    返回 (items, error)：items 为 [(母叶名, Decimal 占比)]，error 为中文提示。
    全部占比相加必须正好等于 100，否则不予保存。
    """
    items = []
    for leaf, raw in pairs:
        leaf = (leaf or "").strip()
        raw = (raw or "").strip()
        if not leaf and not raw:
            continue
        if not leaf or not raw:
            return None, "母叶名与占比要成对填写"
        try:
            percent = Decimal(raw)
        except InvalidOperation:
            return None, f"占比「{raw}」不是有效数字"
        if not percent.is_finite() or percent <= 0 or percent > 100:
            return None, f"母叶「{leaf}」的占比需在 0 到 100 之间"
        items.append((leaf, percent))
    if not items:
        return None, "至少登记一行母叶"
    names = [name for name, _ in items]
    if len(set(names)) != len(names):
        return None, "同一比例尺内母叶名不能重复"
    total = sum(percent for _, percent in items)
    if total != Decimal("100"):
        return None, f"占比合计须正好为 100，当前合计 {total}"
    return items, None
