#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SVG Layer Extractor - 提取SVG分层信息的CLI工具
支持AI Agent查询的通用SVG解析工具
"""

import argparse
import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from lxml import etree
from dataclasses import dataclass, asdict, field
from decimal import Decimal

# 命名空间映射
NAMESPACES = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
    'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd',
    'xlink': 'http://www.w3.org/1999/xlink'
}


@dataclass
class ElementInfo:
    """SVG元素信息数据类"""
    tag: str
    id: Optional[str] = None
    label: Optional[str] = None  # inkscape:label
    title: Optional[str] = None  # <title>子元素
    style: Optional[str] = None
    transform: Optional[str] = None
    display: Optional[str] = None
    visibility: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)
    bbox: Optional[Dict[str, float]] = None  # {x, y, width, height}
    children: List['ElementInfo'] = field(default_factory=list)
    layer_id: Optional[str] = None  # 所属图层ID
    layer_label: Optional[str] = None  # 所属图层标签


@dataclass
class LayerInfo:
    """图层信息数据类"""
    id: Optional[str] = None
    label: Optional[str] = None
    groupmode: Optional[str] = None
    elements: List[ElementInfo] = field(default_factory=list)


@dataclass
class SVGInfo:
    """SVG文件元数据"""
    width: Optional[str] = None
    height: Optional[str] = None
    viewBox: Optional[str] = None
    version: Optional[str] = None
    id: Optional[str] = None


class SVGLayerExtractor:
    """SVG分层信息提取器"""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.tree = None
        self.root = None
        self.svg_info = SVGInfo()
        self.layers: List[LayerInfo] = []
        self.all_elements: List[ElementInfo] = []
        self._parse()
    
    def _parse(self):
        """解析SVG文件"""
        try:
            parser = etree.XMLParser(remove_blank_text=True)
            self.tree = etree.parse(str(self.file_path), parser)
            self.root = self.tree.getroot()
            
            # 注册命名空间以便查询
            for prefix, uri in NAMESPACES.items():
                self.root.register_namespace(prefix, uri)
            
            # 提取SVG元数据
            self._extract_svg_metadata()
            
            # 提取图层
            self._extract_layers()
            
            # 提取所有元素（包括非图层内的）
            self._extract_all_elements()
            
        except Exception as e:
            print(f"Error parsing SVG file: {e}", file=sys.stderr)
            sys.exit(1)
    
    def _extract_svg_metadata(self):
        """提取SVG根元素元数据"""
        svg_attrs = dict(self.root.attrib)
        self.svg_info.width = svg_attrs.get('width')
        self.svg_info.height = svg_attrs.get('height')
        self.svg_info.viewBox = svg_attrs.get('viewBox')
        self.svg_info.version = svg_attrs.get('version')
        self.svg_info.id = svg_attrs.get('id')
    
    def _extract_layers(self):
        """提取图层信息"""
        # 查找所有inkscape图层（g元素，inkscape:groupmode="layer"）
        xpath = "//svg:g[@inkscape:groupmode='layer']"
        layer_elements = self.root.xpath(xpath, namespaces=NAMESPACES)
        
        for layer_elem in layer_elements:
            layer_info = LayerInfo()
            layer_info.id = layer_elem.get('id')
            layer_info.label = layer_elem.get('{http://www.inkscape.org/namespaces/inkscape}label')
            layer_info.groupmode = layer_elem.get('{http://www.inkscape.org/namespaces/inkscape}groupmode')
            
            # 提取图层内元素
            elements = self._extract_elements_from_container(layer_elem, layer_info.id, layer_info.label)
            layer_info.elements = elements
            self.layers.append(layer_info)
    
    def _extract_elements_from_container(self, container, layer_id: Optional[str], layer_label: Optional[str]) -> List[ElementInfo]:
        """从容器元素中提取子元素信息"""
        elements = []
        for child in container:
            if child.tag == '{http://www.w3.org/2000/svg}g':
                # 处理嵌套组
                nested_elements = self._extract_elements_from_container(child, layer_id, layer_label)
                elements.extend(nested_elements)
            else:
                # 处理实际图形元素
                elem_info = self._parse_element(child, layer_id, layer_label)
                if elem_info:
                    elements.append(elem_info)
        return elements
    
    def _parse_element(self, elem, layer_id: Optional[str], layer_label: Optional[str]) -> Optional[ElementInfo]:
        """解析单个SVG元素"""
        # 跳过非图形元素（如title, desc, defs等）
        if elem.tag in ['{http://www.w3.org/2000/svg}title', 
                       '{http://www.w3.org/2000/svg}desc',
                       '{http://www.w3.org/2000/svg}defs',
                       '{http://www.w3.org/2000/svg}style',
                       '{http://www.w3.org/2000/svg}metadata']:
            return None
        
        # 获取标签名（去除命名空间）
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # 提取属性
        attrs = dict(elem.attrib)
        
        # 提取inkscape:label
        label = attrs.pop('{http://www.inkscape.org/namespaces/inkscape}label', None)
        
        # 提取inkscape:groupmode（如果是组）
        groupmode = attrs.pop('{http://www.w3.org/namespaces/inkscape}groupmode', None)
        
        # 提取title子元素
        title_elem = elem.find('{http://www.w3.org/2000/svg}title')
        title = title_elem.text if title_elem is not None else None
        
        # 提取显示属性
        display = attrs.get('display')
        visibility = attrs.get('visibility')
        
        # 计算边界框（如果元素有几何属性）
        bbox = self._calculate_bbox(elem, attrs)
        
        # 处理use元素（引用其他元素）
        if tag == 'use':
            href = attrs.get('{http://www.w3.org/1999/xlink}href') or attrs.get('href')
            if href:
                # 尝试查找被引用的元素
                ref_id = href.lstrip('#')
                ref_elem = self.root.xpath(f"//*[@id='{ref_id}']", namespaces=NAMESPACES)
                if ref_elem:
                    # 复制被引用元素的属性，但保留use的transform
                    pass
        
        return ElementInfo(
            tag=tag,
            id=attrs.pop('id', None),
            label=label,
            title=title,
            style=attrs.pop('style', None),
            transform=attrs.pop('transform', None),
            display=display,
            visibility=visibility,
            attributes=attrs,
            bbox=bbox,
            layer_id=layer_id,
            layer_label=layer_label
        )
    
    def _calculate_bbox(self, elem, attrs) -> Optional[Dict[str, float]]:
        """计算元素的边界框"""
        try:
            # 处理rect
            if elem.tag.endswith('rect'):
                x = float(attrs.get('x', 0))
                y = float(attrs.get('y', 0))
                width = float(attrs.get('width', 0))
                height = float(attrs.get('height', 0))
                return {'x': x, 'y': y, 'width': width, 'height': height}
            
            # 处理circle
            elif elem.tag.endswith('circle'):
                cx = float(attrs.get('cx', 0))
                cy = float(attrs.get('cy', 0))
                r = float(attrs.get('r', 0))
                return {
                    'x': cx - r, 
                    'y': cy - r, 
                    'width': 2*r, 
                    'height': 2*r
                }
            
            # 处理ellipse
            elif elem.tag.endswith('ellipse'):
                cx = float(attrs.get('cx', 0))
                cy = float(attrs.get('cy', 0))
                rx = float(attrs.get('rx', 0))
                ry = float(attrs.get('ry', 0))
                return {
                    'x': cx - rx, 
                    'y': cy - ry, 
                    'width': 2*rx, 
                    'height': 2*ry
                }
            
            # 处理line
            elif elem.tag.endswith('line'):
                x1 = float(attrs.get('x1', 0))
                y1 = float(attrs.get('y1', 0))
                x2 = float(attrs.get('x2', 0))
                y2 = float(attrs.get('y2', 0))
                return {
                    'x': min(x1, x2),
                    'y': min(y1, y2),
                    'width': abs(x2 - x1),
                    'height': abs(y2 - y1)
                }
            
            # 处理path（简化处理）
            elif elem.tag.endswith('path'):
                d = attrs.get('d')
                if d:
                    # 提取path中的数字
                    numbers = [float(n) for n in re.findall(r'-?\d+\.?\d*', d)]
                    if numbers:
                        min_x = min(numbers[::2]) if len(numbers) >= 2 else 0
                        max_x = max(numbers[::2]) if len(numbers) >= 2 else 0
                        min_y = min(numbers[1::2]) if len(numbers) >= 2 else 0
                        max_y = max(numbers[1::2]) if len(numbers) >= 2 else 0
                        return {
                            'x': min_x,
                            'y': min_y,
                            'width': max_x - min_x,
                            'height': max_y - min_y
                        }
            
            return None
        except (ValueError, TypeError):
            return None
    
    def _extract_all_elements(self):
        """提取所有元素（扁平化）"""
        # 遍历所有非g元素
        xpath = "//svg:*[not(self::svg:g) and not(self::svg:title) and not(self::svg:desc) and not(self::svg:metadata)]"
        for elem in self.root.xpath(xpath, namespaces=NAMESPACES):
            # 查找所属图层
            layer_id, layer_label = self._find_parent_layer(elem)
            
            elem_info = self._parse_element(elem, layer_id, layer_label)
            if elem_info:
                self.all_elements.append(elem_info)
    
    def _find_parent_layer(self, elem) -> Tuple[Optional[str], Optional[str]]:
        """查找元素所属的图层"""
        parent = elem.getparent()
        while parent is not None:
            if parent.get('{http://www.inkscape.org/namespaces/inkscape}groupmode') == 'layer':
                return parent.get('id'), parent.get('{http://www.inkscape.org/namespaces/inkscape}label')
            parent = parent.getparent()
        return None, None
    
    def get_full_structure(self) -> Dict[str, Any]:
        """获取完整的SVG结构"""
        return {
            'file': str(self.file_path),
            'metadata': asdict(self.svg_info),
            'layers': [asdict(layer) for layer in self.layers],
            'total_elements': len(self.all_elements)
        }
    
    def query_by_layer(self, layer_name: Optional[str] = None, layer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """按图层查询"""
        results = []
        for layer in self.layers:
            if (layer_name and layer.label and layer_name.lower() in layer.label.lower()) or \
               (layer_id and layer.id and layer_id in layer.id):
                results.append({
                    'layer': asdict(layer),
                    'element_count': len(layer.elements)
                })
        return results
    
    def query_by_element_id(self, element_id: str) -> List[Dict[str, Any]]:
        """按元素ID查询"""
        return [asdict(elem) for elem in self.all_elements if elem.id == element_id]
    
    def query_by_label(self, label: str) -> List[Dict[str, Any]]:
        """按inkscape:label查询（支持模糊匹配）"""
        label_lower = label.lower()
        return [asdict(elem) for elem in self.all_elements 
                if elem.label and label_lower in elem.label.lower()]
    
    def query_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """按元素标签查询"""
        return [asdict(elem) for elem in self.all_elements if elem.tag == tag]
    
    def query_by_attribute(self, attr_name: str, attr_value: str) -> List[Dict[str, Any]]:
        """按属性查询"""
        return [asdict(elem) for elem in self.all_elements 
                if elem.attributes.get(attr_name) == attr_value]
    
    def get_element_stats(self) -> Dict[str, Any]:
        """获取元素统计信息"""
        stats = {
            'total_elements': len(self.all_elements),
            'by_tag': {},
            'by_layer': {},
            'by_visibility': {}
        }
        
        for elem in self.all_elements:
            # 按标签统计
            stats['by_tag'][elem.tag] = stats['by_tag'].get(elem.tag, 0) + 1
            
            # 按图层统计
            layer_key = elem.layer_label or elem.layer_id or 'unlayered'
            stats['by_layer'][layer_key] = stats['by_layer'].get(layer_key, 0) + 1
            
            # 按可见性统计
            vis = elem.display or elem.visibility or 'visible'
            stats['by_visibility'][vis] = stats['by_visibility'].get(vis, 0) + 1
        
        return stats
    
    def export_to_markdown(self) -> str:
        """导出为Markdown格式"""
        md = []
        md.append(f"# SVG Layer Structure: {self.file_path.name}\n")
        md.append(f"**Dimensions:** {self.svg_info.width} x {self.svg_info.height}\n")
        
        for layer in self.layers:
            md.append(f"\n## Layer: {layer.label} (ID: {layer.id})")
            md.append("| ID | Tag | Label | Style | BBox |")
            md.append("|---|---|---|---|---|")
            
            for elem in layer.elements:
                bbox_str = f"{elem.bbox['x']:.2f},{elem.bbox['y']:.2f}" if elem.bbox else "N/A"
                md.append(f"| {elem.id} | `{elem.tag}` | {elem.label or ''} | {elem.style[:30] if elem.style else ''}... | {bbox_str} |")
        
        return '\n'.join(md)


def main():
    parser = argparse.ArgumentParser(
        description='SVG Layer Extractor - Extract hierarchical information from SVG files for AI Agent queries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file.svg                                    # Output full structure
  %(prog)s file.svg --query-type layer --query "road"  # Query by layer name
  %(prog)s file.svg --query-type id --query "rect1"    # Query by element ID
  %(prog)s file.svg --query-type label --query "Path"  # Query by label
  %(prog)s file.svg --query-type tag --query "rect"    # Query by tag
  %(prog)s file.svg --stats                            # Show statistics
  %(prog)s file.svg --format markdown                  # Output as Markdown
        """
    )
    
    parser.add_argument('svg_file', help='Path to SVG file')
    parser.add_argument('--query-type', choices=['layer', 'id', 'label', 'tag', 'attr'], 
                       help='Type of query to perform')
    parser.add_argument('--query', help='Query value')
    parser.add_argument('--attr-name', help='Attribute name (used with --query-type attr)')
    parser.add_argument('--format', choices=['json', 'markdown', 'text'], default='json',
                       help='Output format (default: json)')
    parser.add_argument('--compact', action='store_true', help='Compact JSON output (no indentation)')
    parser.add_argument('--stats', action='store_true', help='Show element statistics')
    parser.add_argument('--indent', type=int, default=2, help='JSON indentation (default: 2)')
    
    args = parser.parse_args()
    
    # 检查文件存在
    if not Path(args.svg_file).exists():
        print(f"Error: File '{args.svg_file}' not found", file=sys.stderr)
        sys.exit(1)
    
    # 解析SVG
    extractor = SVGLayerExtractor(args.svg_file)
    
    # 处理查询
    output_data = None
    
    if args.stats:
        output_data = extractor.get_element_stats()
    elif args.query_type and args.query:
        if args.query_type == 'layer':
            output_data = extractor.query_by_layer(layer_name=args.query)
        elif args.query_type == 'id':
            output_data = extractor.query_by_element_id(args.query)
        elif args.query_type == 'label':
            output_data = extractor.query_by_label(args.query)
        elif args.query_type == 'tag':
            output_data = extractor.query_by_tag(args.query)
        elif args.query_type == 'attr':
            if args.attr_name:
                output_data = extractor.query_by_attribute(args.attr_name, args.query)
            else:
                print("Error: --attr-name required for --query-type attr", file=sys.stderr)
                sys.exit(1)
    else:
        output_data = extractor.get_full_structure()
    
    # 输出结果
    if args.format == 'json':
        indent = None if args.compact else args.indent
        print(json.dumps(output_data, ensure_ascii=False, indent=indent))
    elif args.format == 'markdown':
        if args.query_type:
            print(json.dumps(output_data, ensure_ascii=False, indent=2))
        else:
            print(extractor.export_to_markdown())
    else:
        print(json.dumps(output_data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()