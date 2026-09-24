def weigh(aroma: float, taste: float, liquor: float) -> tuple[str, str, float]:
    score = round(aroma * 0.3 + taste * 0.5 + liquor * 0.2, 2)
    if score >= 7:
        return "通过", "加权分达到放行线", score
    return "不通过", "加权分低于放行线", score


def validate_scale(leaves: list[tuple[str, str]]) -> tuple[list[tuple[str, float]] | None, str | None]:
    """登记母叶占比：母叶名非空不重复，占比为 0~100 的数字，合计必须正好 100。"""
    cleaned: list[tuple[str, float]] = []
    names: set[str] = set()
    for raw_name, raw_percent in leaves:
        name = (raw_name or "").strip()
        if not name:
            return None, "母叶名不能为空"
        if name in names:
            return None, f"母叶重复：{name}"
        try:
            percent = float((raw_percent or "").strip())
        except ValueError:
            return None, f"{name} 的占比不是数字"
        if not (0 < percent <= 100):
            return None, f"{name} 的占比必须在 0 到 100 之间"
        names.add(name)
        cleaned.append((name, percent))
    if not cleaned:
        return None, "至少要登记一种母叶"
    total = round(sum(percent for _, percent in cleaned), 2)
    if total != 100:
        return None, f"占比合计必须正好为 100，当前为 {total:g}"
    return cleaned, None
