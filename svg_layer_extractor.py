#!/usr/bin/env python3
"""
SVG Layer Info Extractor - CLI Tool for AI Agents

A command-line tool to extract layer->label->info hierarchical information 
from Inkscape SVG files. This tool parses SVG files directly without requiring
a full Inkscape installation.

Usage:
    python svg_layer_extractor.py <svg_file> [options]
    
Options:
    --format FORMAT       Output format: json, text, tree (default: json)
    --query QUERY         Query specific layer by label or path
    --search TERM         Search layers by label (case-insensitive)
    --export              Export layer structure to file
    --output FILE         Output file path (for --export)
    --help                Show this help message

Examples:
    python svg_layer_extractor.py design.svg
    python svg_layer_extractor.py design.svg --format tree
    python svg_layer_extractor.py design.svg --query "Background"
    python svg_layer_extractor.py design.svg --search "layer"
"""

import sys
import os
import json
import argparse
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path


# Inkscape namespace
INKSCAPE_NS = '{http://www.inkscape.org/namespaces/inkscape}'
SVG_NS = '{http://www.w3.org/2000/svg}'
SODIPODI_NS = '{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}'

@dataclass
class LayerInfo:
    """Represents a layer with its metadata"""
    id: str
    label: str
    level: int
    parent_id: Optional[str]
    children: List['LayerInfo']
    attributes: Dict[str, str]
    xpath: str
    description: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary, excluding empty fields"""
        result = {
            'id': self.id,
            'label': self.label,
            'level': self.level,
            'xpath': self.xpath,
        }
        
        if self.parent_id:
            result['parent_id'] = self.parent_id
            
        if self.description:
            result['description'] = self.description
            
        if self.attributes:
            # Filter out common non-informative attributes
            filtered_attrs = {k: v for k, v in self.attributes.items() 
                            if not k.startswith('{')}
            if filtered_attrs:
                result['attributes'] = filtered_attrs
                
        if self.children:
            result['children'] = [child.to_dict() for child in self.children]
            
        return result


class SVGLayerExtractor:
    """Extract layer information from Inkscape SVG files"""
    
    def __init__(self, svg_path: str):
        self.svg_path = Path(svg_path)
        if not self.svg_path.exists():
            raise FileNotFoundError(f"SVG file not found: {svg_path}")
        
        self.tree = None
        self.root = None
        self.layers: List[LayerInfo] = []
        self.layer_map: Dict[str, LayerInfo] = {}
        
    def parse(self) -> None:
        """Parse the SVG file and extract layer information"""
        try:
            self.tree = ET.parse(str(self.svg_path))
            self.root = self.tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Invalid SVG file: {e}")
        
        self._extract_layers()
        
    def _extract_layers(self) -> None:
        """Extract all layers from the SVG"""
        self.layers = []
        self.layer_map = {}
        
        # Find all group elements that are Inkscape layers
        self._find_layers_recursive(self.root, None, 0, [])
        
    def _find_layers_recursive(self, element: ET.Element, 
                                parent_id: Optional[str],
                                level: int,
                                path: List[str]) -> None:
        """Recursively find all layer elements"""
        
        # Check if this element is a layer
        is_layer = element.tag == f'{SVG_NS}g'
        layer_label = element.get(f'{INKSCAPE_NS}label')
        is_group = element.get(f'{INKSCAPE_NS}groupmode') == 'layer'
        
        if is_layer and layer_label:
            # Build xpath
            current_path = path + [layer_label]
            xpath = '/'.join(current_path)
            
            # Extract additional info
            description = element.get(f'{SODIPODI_NS}docname')
            
            # Get all attributes
            attributes = dict(element.attrib)
            
            # Create layer info
            layer_id = element.get('id', f'layer_{len(self.layers)}')
            layer_info = LayerInfo(
                id=layer_id,
                label=layer_label,
                level=level,
                parent_id=parent_id,
                children=[],
                attributes=attributes,
                xpath=xpath,
                description=description
            )
            
            # Add to parent's children or top-level layers
            if parent_id and parent_id in self.layer_map:
                self.layer_map[parent_id].children.append(layer_info)
            else:
                self.layers.append(layer_info)
                
            # Store in map for quick lookup
            self.layer_map[layer_id] = layer_info
            
            # Process children
            for child in element:
                self._find_layers_recursive(child, layer_id, level + 1, current_path)
                
        elif is_layer:
            # It's a group but not a labeled layer, still check children
            for child in element:
                self._find_layers_recursive(child, parent_id, level, path)
        else:
            # Not a group element, check all children
            for child in element:
                self._find_layers_recursive(child, parent_id, level, path)
    
    def get_layers(self) -> List[LayerInfo]:
        """Get all extracted layers"""
        return self.layers
    
    def query_by_label(self, label: str) -> Optional[LayerInfo]:
        """Query a layer by its exact label"""
        for layer in self.layer_map.values():
            if layer.label == label:
                return layer
        return None
    
    def search_layers(self, term: str) -> List[LayerInfo]:
        """Search layers by label (case-insensitive)"""
        term_lower = term.lower()
        results = []
        for layer in self.layer_map.values():
            if term_lower in layer.label.lower():
                results.append(layer)
        return results
    
    def query_by_xpath(self, xpath: str) -> Optional[LayerInfo]:
        """Query a layer by its xpath"""
        for layer in self.layer_map.values():
            if layer.xpath == xpath:
                return layer
        return None
    
    def to_json(self, indent: int = 2) -> str:
        """Export layer structure as JSON"""
        data = {
            'file': str(self.svg_path),
            'total_layers': len(self.layer_map),
            'layers': [layer.to_dict() for layer in self.layers]
        }
        return json.dumps(data, indent=indent, ensure_ascii=False)
    
    def to_text(self) -> str:
        """Export layer structure as plain text"""
        lines = []
        lines.append(f"File: {self.svg_path}")
        lines.append(f"Total Layers: {len(self.layer_map)}")
        lines.append("")
        
        for layer in self.layers:
            self._add_layer_to_text(layer, lines, 0)
            
        return '\n'.join(lines)
    
    def _add_layer_to_text(self, layer: LayerInfo, lines: List[str], indent: int) -> None:
        """Add a layer to text output"""
        prefix = "  " * indent
        lines.append(f"{prefix}[{layer.id}] {layer.label}")
        
        if layer.description:
            lines.append(f"{prefix}  Description: {layer.description}")
            
        for child in layer.children:
            self._add_layer_to_text(child, lines, indent + 1)
    
    def to_tree(self) -> str:
        """Export layer structure as ASCII tree"""
        lines = []
        lines.append(f"📁 {self.svg_path.name} ({len(self.layer_map)} layers)")
        
        for i, layer in enumerate(self.layers):
            is_last = i == len(self.layers) - 1
            self._add_layer_to_tree(layer, lines, "", is_last)
            
        return '\n'.join(lines)
    
    def _add_layer_to_tree(self, layer: LayerInfo, lines: List[str], 
                           prefix: str, is_last: bool) -> None:
        """Add a layer to tree output"""
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}📂 {layer.label} [{layer.id}]")
        
        child_prefix = prefix + ("    " if is_last else "│   ")
        
        for i, child in enumerate(layer.children):
            child_is_last = i == len(layer.children) - 1
            self._add_layer_to_tree(child, lines, child_prefix, child_is_last)


def create_agent_response(extractor: SVGLayerExtractor, 
                         query: Optional[str] = None,
                         search: Optional[str] = None,
                         format: str = 'json') -> Dict:
    """Create a structured response for AI agents"""
    
    response = {
        'success': True,
        'file': str(extractor.svg_path),
        'total_layers': len(extractor.layer_map),
    }
    
    if query:
        layer = extractor.query_by_label(query)
        if layer:
            response['query_result'] = layer.to_dict()
        else:
            response['success'] = False
            response['error'] = f"Layer '{query}' not found"
            
    elif search:
        results = extractor.search_layers(search)
        response['search_term'] = search
        response['search_results'] = [r.to_dict() for r in results]
        response['match_count'] = len(results)
        
    else:
        if format == 'json':
            response['structure'] = json.loads(extractor.to_json())
        elif format == 'text':
            response['structure'] = extractor.to_text()
        elif format == 'tree':
            response['structure'] = extractor.to_tree()
            
    return response


def main():
    parser = argparse.ArgumentParser(
        description='Extract layer information from Inkscape SVG files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('svg_file', help='Path to the SVG file')
    parser.add_argument('--format', '-f', choices=['json', 'text', 'tree'],
                       default='json', help='Output format (default: json)')
    parser.add_argument('--query', '-q', help='Query specific layer by label')
    parser.add_argument('--search', '-s', help='Search layers by label')
    parser.add_argument('--export', '-e', action='store_true',
                       help='Export to file')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--agent', '-a', action='store_true',
                       help='Format output for AI agent consumption')
    
    args = parser.parse_args()
    
    try:
        # Create extractor and parse
        extractor = SVGLayerExtractor(args.svg_file)
        extractor.parse()
        
        # Generate output
        if args.agent:
            response = create_agent_response(
                extractor,
                query=args.query,
                search=args.search,
                format=args.format
            )
            output = json.dumps(response, indent=2, ensure_ascii=False)
        elif args.query:
            layer = extractor.query_by_label(args.query)
            if layer:
                if args.format == 'json':
                    output = json.dumps(layer.to_dict(), indent=2, ensure_ascii=False)
                else:
                    output = f"Label: {layer.label}\nID: {layer.id}\nXPath: {layer.xpath}"
            else:
                print(f"Error: Layer '{args.query}' not found", file=sys.stderr)
                sys.exit(1)
        elif args.search:
            results = extractor.search_layers(args.search)
            if args.format == 'json':
                output = json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False)
            else:
                output = f"Found {len(results)} matching layers:\n"
                for r in results:
                    output += f"  - {r.label} ({r.id})\n"
        else:
            if args.format == 'json':
                output = extractor.to_json()
            elif args.format == 'text':
                output = extractor.to_text()
            elif args.format == 'tree':
                output = extractor.to_tree()
        
        # Output
        if args.export and args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"Exported to {args.output}")
        else:
            print(output)
            
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
