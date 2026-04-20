
"""
AI Agent 使用示例：如何调用SVG分层信息提取工具
"""

import subprocess
import json

class SVGAgentTool:
    """AI Agent的SVG工具包装器"""

    def __init__(self, tool_path='svg_layer_tool.py'):
        self.tool_path = tool_path

    def _run(self, args):
        """执行CLI命令"""
        cmd = ['python', self.tool_path] + args
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"工具执行失败: {result.stderr}")
        return json.loads(result.stdout)

    def get_structure(self, svg_file):
        """获取SVG完整分层结构"""
        return self._run(['query', 'structure', svg_file])

    def get_layers(self, svg_file):
        """获取所有图层列表"""
        return self._run(['query', 'layers', svg_file])

    def find_by_id(self, svg_file, elem_id):
        """通过ID查找元素"""
        return self._run(['query', 'by_id', '--id', elem_id, svg_file])

    def find_by_tag(self, svg_file, tag):
        """通过标签名查找元素"""
        return self._run(['query', 'by_tag', '--tag', tag, svg_file])

    def find_by_label(self, svg_file, pattern):
        """通过标签名模糊查找"""
        return self._run(['query', 'by_label', '--pattern', pattern, svg_file])

    def get_geometry(self, svg_file):
        """获取几何信息"""
        return self._run(['query', 'geometry', svg_file])

    def analyze_road_map(self, svg_file):
        """专门用于分析道路地图的AI Agent方法"""
        geometry = self.get_geometry(svg_file)

        # 识别道路（黑色矩形）
        roads = [g for g in geometry if g.get('style', {}).get('fill') == '#000000']

        # 识别建筑物（橙色矩形）
        buildings = [g for g in geometry if g.get('style', {}).get('fill') == '#ff7f2a']

        # 识别引用（use元素）
        uses = self.find_by_tag(svg_file, 'use')

        return {
            'roads': roads,
            'buildings': buildings,
            'references': uses,
            'summary': {
                'total_roads': len(roads),
                'total_buildings': len(buildings),
                'total_references': len(uses)
            }
        }


# ==================== AI Agent使用示例 ====================

if __name__ == '__main__':
    # 初始化工具
    tool = SVGAgentTool('svg_layer_tool.py')
    svg_file = 'road_test.svg'

    # 示例1: Agent分析道路地图
    print("=" * 60)
    print("AI Agent分析道路地图")
    print("=" * 60)
    analysis = tool.analyze_road_map(svg_file)
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

    # 示例2: Agent查找特定建筑物
    print("
" + "=" * 60)
    print("查找标记为 'building_center' 的元素")
    print("=" * 60)
    buildings = tool.find_by_label(svg_file, 'building')
    print(json.dumps(buildings, indent=2, ensure_ascii=False))

    # 示例3: Agent获取道路Path信息
    print("
" + "=" * 60)
    print("查找所有Path相关元素")
    print("=" * 60)
    paths = tool.find_by_label(svg_file, 'Path')
    print(json.dumps(paths, indent=2, ensure_ascii=False))
