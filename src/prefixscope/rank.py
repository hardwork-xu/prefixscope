"""Compacting last-touch Fenwick index. / 可压缩的最近访问 Fenwick 索引。"""

from array import array


class RankIndex:
    """Maintain exact 1-based LRU ranks. / 维护从 1 开始的精确 LRU 排名。

    Every live ID owns one occupied timestamp. Compaction monotonically relabels
    timestamps and therefore preserves every rank. Disabled compaction retains
    a growing time axis for the memory ablation.
    每个已知标识占用一个时间戳。压缩按原顺序重新编号，因此保持全部排名。
    关闭压缩时保留持续增长的时间轴，用于内存消融实验。
    """

    def __init__(self, *, compact: bool, initial_slots: int) -> None:
        self.compact = compact
        self.slots = initial_slots
        self.positions: dict[str, int] = {}
        self.tree = array("q", [0]) * (self.slots + 1)
        self.clock = 0
        self.compactions = 0

    def rank(self, block: str) -> int | None:
        """Read the current rank without mutation. / 只读查询当前排名。"""
        position = self.positions.get(block)
        if position is None:
            return None
        older_or_equal = 0
        while position:
            older_or_equal += self.tree[position]
            position -= position & -position
        return len(self.positions) - older_or_equal + 1

    def _add(self, position: int, delta: int) -> None:
        while position <= self.slots:
            self.tree[position] += delta
            position += position & -position

    def _make_room(self) -> None:
        if self.clock < self.slots:
            return
        if self.compact and len(self.positions) <= self.slots // 2:
            ordered = sorted(self.positions, key=self.positions.__getitem__)
            self.positions = {block: index for index, block in enumerate(ordered, 1)}
            self.clock = len(ordered)
            self.compactions += 1
        else:
            self.slots *= 2
        # Linear Fenwick construction from occupied points. / 从占用点线性构造树。
        self.tree = array("q", [0]) * (self.slots + 1)
        for position in self.positions.values():
            self.tree[position] = 1
        for index in range(1, self.slots + 1):
            parent = index + (index & -index)
            if parent <= self.slots:
                self.tree[parent] += self.tree[index]

    def touch(self, block: str) -> None:
        """Move one page to the most-recent position. / 将一页移到最近访问位置。"""
        self._make_room()
        previous = self.positions.get(block)
        if previous is not None:
            self._add(previous, -1)
        self.clock += 1
        self.positions[block] = self.clock
        self._add(self.clock, 1)
