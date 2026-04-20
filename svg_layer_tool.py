#!/usr/bin/env python3
"""
SVG分层信息提取CLI工具
用于解析SVG文件，提取分层结构信息，支持AI Agent查询
"""

import xml.etree.ElementTree as ET
import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class SVGElement:
    """SVG元素数据结构"""
    id: str
    tag: str
    label: Optional[str] = None
    parent_layer: Optional[str] = None
    attributes: Dict[str, str] = None
    children: List['SVGElement'] = None
    text_content: Optional[str] = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}
        if self.children is None:
            self.children = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tag': self.tag,
            'label': self.label,
            'parent_layer': self.parent_layer,
            'attributes': self.attributes,
            'text_content': self.text_content,
            'children': [c.to_dict() for c in self.children]
        }


@dataclass
class SVGLayer:
    """SVG图层数据结构"""
    id: str
    label: str
    index: int
    elements: List[SVGElement]
    attributes: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'label': self.label,
            'index': self.index,
            'attributes': self.attributes,
            'elements': [e.to_dict() for e in self.elements]
        }


class SVGParser:
    """SVG解析器"""

    # SVG命名空间
    NAMESPACES = {
        'svg': 'http://www.w3.org/2000/svg',
        'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
        'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd',
        'xlink': 'http://www.w3.org/1999/xlink'
    }

    def __init__(self, svg_path: str):
        self.svg_path = Path(svg_path)
        self.tree = None
        self.root = None
        self.layers: List[SVGLayer] = []
        self.all_elements: Dict[str, SVGElement] = {}
        self.defs: Dict[str, SVGElement] = {}

    def parse(self) -> 'SVGParser':
        """解析SVG文件"""
        try:
            # 注册命名空间
            for prefix, uri in self.NAMESPACES.items():
                ET.register_namespace(prefix, uri)

            self.tree = ET.parse(self.svg_path)
            self.root = self.tree.getroot()

            # 提取defs定义
            self._extract_defs()

            # 提取图层信息
            self._extract_layers()

            return self
        except Exception as e:
            raise ValueError(f"解析SVG文件失败: {e}")

    def _extract_defs(self):
        """提取defs中的定义元素"""
        defs = self.root.find('.//svg:defs', self.NAMESPACES)
        if defs is not None:
            for elem in defs:
                elem_id = elem.get('id', '')
                if elem_id:
                    self.defs[elem_id] = self._create_element(elem, None)

    def _extract_layers(self):
        """提取图层结构"""
        layer_index = 0

        # 查找所有g元素（图层）
        for g in self.root.findall('.//svg:g', self.NAMESPACES):
            group_mode = g.get('{http://www.inkscape.org/namespaces/inkscape}groupmode')

            # Inkscape图层标记
            if group_mode == 'layer':
                layer_id = g.get('id', f'layer_{layer_index}')
                layer_label = g.get('{http://www.inkscape.org/namespaces/inkscape}label', layer_id)

                # 提取该图层下的所有元素
                elements = self._extract_layer_elements(g, layer_id)

                layer = SVGLayer(
                    id=layer_id,
                    label=layer_label,
                    index=layer_index,
                    elements=elements,
                    attributes=dict(g.attrib)
                )

                self.layers.append(layer)
                layer_index += 1

        # 如果没有找到Inkscape图层，将整个SVG作为一个图层处理
        if not self.layers:
            elements = self._extract_layer_elements(self.root, 'root')
            self.layers.append(SVGLayer(
                id='root',
                label='Root',
                index=0,
                elements=elements,
                attributes=dict(self.root.attrib)
            ))

    def _extract_layer_elements(self, parent, layer_id: str) -> List[SVGElement]:
        """递归提取图层内的元素"""
        elements = []

        for child in parent:
            tag = child.tag.replace('{http://www.w3.org/2000/svg}', '').replace('{http://www.w3.org/1999/xlink}', '')

            # 跳过defs和嵌套的g（子图层）
            if tag in ['defs', 'sodipodi:namedview']:
                continue
            if tag == 'g' and child.get('{http://www.inkscape.org/namespaces/inkscape}groupmode') == 'layer':
                continue

            elem = self._create_element(child, layer_id)
            elements.append(elem)
            self.all_elements[elem.id] = elem

            # 递归处理子元素
            if len(child) > 0:
                elem.children = self._extract_layer_elements(child, layer_id)

        return elements

    def _create_element(self, xml_elem, layer_id: str) -> SVGElement:
        """从XML元素创建SVGElement"""
        tag = xml_elem.tag
        if '}' in tag:
            tag = tag.split('}')[1]

        elem_id = xml_elem.get('id', '')

        # 获取Inkscape标签
        label = xml_elem.get('{http://www.inkscape.org/namespaces/inkscape}label')
        if not label:
            label = xml_elem.get('{http://www.w3.org/1999/xlink}href', '').replace('#', '')

        # 获取文本内容
        text_content = None
        if tag in ['title', 'desc', 'text']:
            text_content = ''.join(xml_elem.itertext()).strip()

        # 处理xlink:href引用
        href = xml_elem.get('{http://www.w3.org/1999/xlink}href', '')
        if href.startswith('#'):
            ref_id = href[1:]
            if ref_id in self.defs:
                ref_elem = self.defs[ref_id]
                if not label:
                    label = ref_elem.label or ref_id

        return SVGElement(
            id=elem_id,
            tag=tag,
            label=label,
            parent_layer=layer_id,
            attributes=dict(xml_elem.attrib),
            text_content=text_content
        )

    def get_structure(self) -> Dict[str, Any]:
        """获取完整的分层结构"""
        return {
            'file': str(self.svg_path),
            'viewBox': self.root.get('viewBox', ''),
            'width': self.root.get('width', ''),
            'height': self.root.get('height', ''),
            'layers': [layer.to_dict() for layer in self.layers],
            'defs': {k: v.to_dict() for k, v in self.defs.items()}
        }

    def find_by_id(self, elem_id: str) -> Optional[SVGElement]:
        """通过ID查找元素"""
        return self.all_elements.get(elem_id)

    def find_by_tag(self, tag: str) -> List[SVGElement]:
        """通过标签名查找元素"""
        results = []
        for layer in self.layers:
            results.extend(self._find_by_tag_recursive(layer.elements, tag))
        return results

    def _find_by_tag_recursive(self, elements: List[SVGElement], tag: str) -> List[SVGElement]:
        """递归查找标签"""
        results = []
        for elem in elements:
            if elem.tag == tag:
                results.append(elem)
            if elem.children:
                results.extend(self._find_by_tag_recursive(elem.children, tag))
        return results

    def find_by_label(self, label_pattern: str) -> List[SVGElement]:
        """通过标签名称模糊查找元素"""
        results = []
        for layer in self.layers:
            results.extend(self._find_by_label_recursive(layer.elements, label_pattern))
        return results

    def _find_by_label_recursive(self, elements: List[SVGElement], pattern: str) -> List[SVGElement]:
        """递归查找标签名称"""
        results = []
        pattern_lower = pattern.lower()
        for elem in elements:
            if elem.label and pattern_lower in elem.label.lower():
                results.append(elem)
            if elem.children:
                results.extend(self._find_by_label_recursive(elem.children, pattern))
        return results

    def get_layer_by_name(self, name: str) -> Optional[SVGLayer]:
        """通过名称获取图层"""
        for layer in self.layers:
            if layer.label == name or layer.id == name:
                return layer
        return None

    def get_elements_by_layer(self, layer_name: str) -> List[Dict[str, Any]]:
        """获取指定图层的所有元素，还原use引用并简化输出"""
        layer = self.get_layer_by_name(layer_name)
        if not layer:
            return []

        result = []
        for elem in layer.elements:
            processed = self._process_element_for_output(elem)
            if processed:
                result.append(processed)
        return result

    def _process_element_for_output(self, elem: SVGElement) -> Optional[Dict[str, Any]]:
        """处理元素：还原use引用，解析transform，简化输出格式"""
        attrs = elem.attributes

        # 解析transform
        transform_x, transform_y = 0.0, 0.0
        transform = attrs.get('transform', '')
        if transform:
            tx, ty = self._parse_translate(transform)
            transform_x, transform_y = tx, ty

        # 检查是否是use元素（副本）
        href = attrs.get('{http://www.w3.org/1999/xlink}href', '')
        if not href:
            href = attrs.get('href', '')

        if href.startswith('#'):
            # 这是副本，需要找到原元素
            ref_id = href[1:]
            original = self.find_by_id(ref_id)
            if original:
                # 基于原元素创建新属性
                base_attrs = dict(original.attributes)
                base_attrs['id'] = elem.id  # 保留副本的ID
                if elem.label:
                    base_attrs['inkscape:label'] = elem.label
                attrs = base_attrs
            else:
                # 找不到原元素，使用当前元素
                pass

        # 构建输出
        output = {
            'id': elem.id,
            'tag': elem.tag if not href else self.find_by_id(href[1:]).tag if href and self.find_by_id(href[1:]) else elem.tag,
            'label': elem.label or ''
        }

        # 计算最终位置（原位置 + transform偏移）
        if 'x' in attrs:
            output['x'] = float(attrs['x']) + transform_x
        if 'y' in attrs:
            output['y'] = float(attrs['y']) + transform_y
        if 'width' in attrs:
            output['width'] = float(attrs['width'])
        if 'height' in attrs:
            output['height'] = float(attrs['height'])

        # 提取颜色
        color = self._extract_color(attrs)
        if color:
            output['color'] = color

        return output

    def _parse_translate(self, transform: str) -> tuple:
        """解析transform=\"translate(x,y)\""""
        import re
        match = re.search(r'translate\s*\(\s*([^,\s]+)\s*,?\s*([^\)]*)\s*\)', transform)
        if match:
            x = float(match.group(1))
            y = float(match.group(2)) if match.group(2) else 0.0
            return x, y
        return 0.0, 0.0

    def _extract_color(self, attrs: Dict[str, str]) -> Optional[str]:
        """从style或fill属性中提取颜色"""
        # 优先从style中解析
        style = attrs.get('style', '')
        if 'fill:' in style:
            import re
            match = re.search(r'fill:([^;\s]+)', style)
            if match:
                return match.group(1)

        # 从fill属性获取
        fill = attrs.get('fill', '')
        if fill and fill != 'none':
            return fill

        return None

    def get_geometry_info(self) -> List[Dict[str, Any]]:
        """提取几何信息（位置、尺寸）"""
        geometry = []

        for elem_id, elem in self.all_elements.items():
            attrs = elem.attributes
            info = {
                'id': elem_id,
                'tag': elem.tag,
                'label': elem.label,
                'layer': elem.parent_layer
            }

            # 提取位置信息
            if 'x' in attrs and 'y' in attrs:
                info['position'] = {'x': float(attrs['x']), 'y': float(attrs['y'])}
            if 'width' in attrs:
                info['width'] = float(attrs['width'])
            if 'height' in attrs:
                info['height'] = float(attrs['height'])
            if 'transform' in attrs:
                info['transform'] = attrs['transform']

            # 提取样式信息
            if 'style' in attrs:
                info['style'] = self._parse_style(attrs['style'])
            if 'fill' in attrs:
                info['fill'] = attrs['fill']
            if 'stroke' in attrs:
                info['stroke'] = attrs['stroke']

            geometry.append(info)

        return geometry

    def _parse_style(self, style_str: str) -> Dict[str, str]:
        """解析style属性"""
        styles = {}
        for item in style_str.split(';'):
            if ':' in item:
                k, v = item.split(':', 1)
                styles[k.strip()] = v.strip()
        return styles

    def query(self, query_type: str, **kwargs) -> Any:
        """通用查询接口"""
        if query_type == 'by_id':
            return self.find_by_id(kwargs.get('id'))
        elif query_type == 'by_tag':
            return self.find_by_tag(kwargs.get('tag'))
        elif query_type == 'by_label':
            return self.find_by_label(kwargs.get('pattern'))
        elif query_type == 'by_layer':
            return self.get_elements_by_layer(kwargs.get('name'))
        elif query_type == 'layer':
            return self.get_layer_by_name(kwargs.get('name'))
        elif query_type == 'geometry':
            return self.get_geometry_info()
        elif query_type == 'structure':
            return self.get_structure()
        elif query_type == 'layers':
            return [{'id': l.id, 'label': l.label, 'index': l.index} for l in self.layers]
        else:
            raise ValueError(f"未知查询类型: {query_type}")


class SVGCLI:
    """CLI接口"""

    def __init__(self):
        self.parser = None
        self.current_svg: Optional[SVGParser] = None

    def run(self):
        """运行CLI"""
        parser = argparse.ArgumentParser(
            description='SVG分层信息提取工具 - 供AI Agent使用',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例:
  python svg_tool.py parse road_test.svg                    # 解析SVG文件
  python svg_tool.py query structure road_test.svg            # 获取完整结构
  python svg_tool.py query layers road_test.svg               # 获取图层列表
  python svg_tool.py query by_id --id rect1 road_test.svg     # 通过ID查询元素
  python svg_tool.py query by_tag --tag rect road_test.svg    # 通过标签查询
  python svg_tool.py query by_label --pattern Path road_test.svg  # 通过标签名模糊查询
  python svg_tool.py query by_layer --name "图层 1" road_test.svg  # 通过图层名查询元素
  python svg_tool.py query geometry road_test.svg            # 获取几何信息
            """
        )

        subparsers = parser.add_subparsers(dest='command', help='可用命令')

        # parse命令
        parse_parser = subparsers.add_parser('parse', help='解析SVG文件')
        parse_parser.add_argument('file', help='SVG文件路径')
        parse_parser.add_argument('-o', '--output', help='输出JSON文件路径')
        parse_parser.add_argument('--pretty', action='store_true', help='美化JSON输出')

        # query命令
        query_parser = subparsers.add_parser('query', help='查询SVG信息')
        query_parser.add_argument('query_type', 
            choices=['structure', 'layers', 'by_id', 'by_tag', 'by_label', 'by_layer', 'layer', 'geometry'],
            help='查询类型')
        query_parser.add_argument('file', help='SVG文件路径')
        query_parser.add_argument('--id', help='元素ID（用于by_id查询）')
        query_parser.add_argument('--tag', help='标签名（用于by_tag查询）')
        query_parser.add_argument('--pattern', help='标签名模式（用于by_label查询）')
        query_parser.add_argument('--name', help='图层名称（用于layer查询）')
        query_parser.add_argument('-o', '--output', help='输出JSON文件路径')
        query_parser.add_argument('--pretty', action='store_true', help='美化JSON输出')

        # interactive命令
        interactive_parser = subparsers.add_parser('interactive', help='交互式查询模式')
        interactive_parser.add_argument('file', help='SVG文件路径')

        args = parser.parse_args()

        if not args.command:
            parser.print_help()
            return

        try:
            if args.command == 'parse':
                self._cmd_parse(args)
            elif args.command == 'query':
                self._cmd_query(args)
            elif args.command == 'interactive':
                self._cmd_interactive(args)
        except Exception as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)

    def _cmd_parse(self, args):
        """执行parse命令"""
        svg = SVGParser(args.file).parse()
        structure = svg.get_structure()

        output = json.dumps(structure, indent=2 if args.pretty else None, ensure_ascii=False)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"结果已保存到: {args.output}")
        else:
            print(output)

    def _cmd_query(self, args):
        """执行query命令"""
        svg = SVGParser(args.file).parse()

        query_params = {'query_type': args.query_type}

        if args.id:
            query_params['id'] = args.id
        if args.tag:
            query_params['tag'] = args.tag
        if args.pattern:
            query_params['pattern'] = args.pattern
        if args.name:
            query_params['name'] = args.name

        result = svg.query(**query_params)

        # 转换结果为可序列化格式
        if isinstance(result, SVGElement):
            result = result.to_dict()
        elif isinstance(result, SVGLayer):
            result = result.to_dict()
        elif isinstance(result, list) and len(result) > 0:
            if isinstance(result[0], SVGElement):
                result = [r.to_dict() for r in result]

        output = json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"结果已保存到: {args.output}")
        else:
            print(output)

    def _cmd_interactive(self, args):
        """交互式查询模式"""
        svg = SVGParser(args.file).parse()

        print(f"\n已加载SVG文件: {args.file}")
        print(f"图层数量: {len(svg.layers)}")
        print(f"元素总数: {len(svg.all_elements)}")
        print("\n可用命令: structure, layers, geometry, by_id <id>, by_tag <tag>, by_label <pattern>, layer <name>, quit")

        while True:
            try:
                cmd = input("\n> ").strip().split()
                if not cmd:
                    continue

                if cmd[0] == 'quit':
                    break
                elif cmd[0] == 'structure':
                    print(json.dumps(svg.get_structure(), indent=2, ensure_ascii=False))
                elif cmd[0] == 'layers':
                    for layer in svg.layers:
                        print(f"  [{layer.index}] {layer.id}: {layer.label}")
                elif cmd[0] == 'geometry':
                    print(json.dumps(svg.get_geometry_info(), indent=2, ensure_ascii=False))
                elif cmd[0] == 'by_id' and len(cmd) > 1:
                    result = svg.find_by_id(cmd[1])
                    if result:
                        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
                    else:
                        print(f"未找到ID: {cmd[1]}")
                elif cmd[0] == 'by_tag' and len(cmd) > 1:
                    results = svg.find_by_tag(cmd[1])
                    print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
                elif cmd[0] == 'by_label' and len(cmd) > 1:
                    results = svg.find_by_label(cmd[1])
                    print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
                elif cmd[0] == 'layer' and len(cmd) > 1:
                    layer = svg.get_layer_by_name(cmd[1])
                    if layer:
                        print(json.dumps(layer.to_dict(), indent=2, ensure_ascii=False))
                    else:
                        print(f"未找到图层: {cmd[1]}")
                else:
                    print("未知命令")
            except KeyboardInterrupt:
                print("\n退出")
                break
            except Exception as e:
                print(f"错误: {e}")


def main():
    """主入口"""
    cli = SVGCLI()
    cli.run()


if __name__ == '__main__':
    main()
