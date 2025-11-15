#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha Arena 版本管理脚本
用于更新版本信息和生成发布说明
"""

import os
import re
from datetime import datetime
from typing import Dict, List


class VersionManager:
    """版本管理器"""
    
    def __init__(self):
        self.version_file = "VERSION.md"
        self.changelog_file = "CHANGELOG.md"
        self.readme_file = "README.md"
    
    def get_current_version(self) -> str:
        """获取当前版本号"""
        try:
            with open(self.version_file, 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'## 当前版本：v(\d+\.\d+\.\d+)', content)
                if match:
                    return match.group(1)
        except FileNotFoundError:
            pass
        return "0.1.0"
    
    def update_version(self, new_version: str, version_type: str = "patch"):
        """
        更新版本号
        
        Args:
            new_version: 新版本号
            version_type: 版本类型 (major, minor, patch)
        """
        current_version = self.get_current_version()
        
        print(f"🔄 更新版本: {current_version} -> {new_version}")
        
        # 更新VERSION.md
        self._update_version_file(new_version)
        
        # 更新README.md中的版本标识
        self._update_readme_version(new_version)
        
        # 更新CHANGELOG.md
        self._update_changelog(new_version, version_type)
        
        print(f"✅ 版本更新完成: v{new_version}")
    
    def _update_version_file(self, version: str):
        """更新VERSION.md文件"""
        try:
            with open(self.version_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 替换版本号
            content = re.sub(
                r'## 当前版本：v\d+\.\d+\.\d+',
                f'## 当前版本：v{version}',
                content
            )
            
            # 更新发布日期
            today = datetime.now().strftime('%Y-%m-%d')
            content = re.sub(
                r'\*\*发布日期\*\*：\d{4}-\d{2}-\d{2}',
                f'**发布日期**：{today}',
                content
            )
            
            with open(self.version_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except FileNotFoundError:
            print(f"❌ 未找到 {self.version_file}")
    
    def _update_readme_version(self, version: str):
        """更新README.md中的版本标识"""
        try:
            with open(self.readme_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 更新版本标识
            content = re.sub(
                r'\[!\[Version\].*?\]\(VERSION\.md\)',
                f'[![Version](https://img.shields.io/badge/version-v{version}--MVP-blue.svg)](VERSION.md)',
                content
            )
            
            # 更新快速开始部分的版本
            content = re.sub(
                r'### 当前版本：v\d+\.\d+\.\d+',
                f'### 当前版本：v{version}',
                content
            )
            
            with open(self.readme_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except FileNotFoundError:
            print(f"❌ 未找到 {self.readme_file}")
    
    def _update_changelog(self, version: str, version_type: str):
        """更新CHANGELOG.md"""
        try:
            with open(self.changelog_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 在[未发布]后添加新版本
            new_entry = f"""
## [{version}] - {today}

### 新增
- 待添加新功能

### 变更
- 待添加变更内容

### 修复
- 待添加修复内容

"""
            
            # 替换[未发布]部分
            content = content.replace(
                "## [未发布]",
                f"## [未发布]\n{new_entry}"
            )
            
            with open(self.changelog_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except FileNotFoundError:
            print(f"❌ 未找到 {self.changelog_file}")
    
    def generate_release_notes(self, version: str) -> str:
        """生成发布说明"""
        try:
            with open(self.changelog_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取指定版本的变更内容
            pattern = rf'## \[{re.escape(version)}\].*?(?=## \[|\Z)'
            match = re.search(pattern, content, re.DOTALL)
            
            if match:
                return match.group(0).strip()
            else:
                return f"版本 {version} 的变更内容未找到"
                
        except FileNotFoundError:
            return f"无法读取 {self.changelog_file}"
    
    def list_versions(self) -> List[str]:
        """列出所有版本"""
        try:
            with open(self.changelog_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取所有版本号
            versions = re.findall(r'## \[(\d+\.\d+\.\d+)\]', content)
            return versions
            
        except FileNotFoundError:
            return []


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python version_manager.py current          # 显示当前版本")
        print("  python version_manager.py list             # 列出所有版本")
        print("  python version_manager.py update <version> # 更新版本")
        print("  python version_manager.py release <version> # 生成发布说明")
        return
    
    manager = VersionManager()
    command = sys.argv[1]
    
    if command == "current":
        version = manager.get_current_version()
        print(f"当前版本: v{version}")
        
    elif command == "list":
        versions = manager.list_versions()
        print("所有版本:")
        for v in versions:
            print(f"  v{v}")
            
    elif command == "update":
        if len(sys.argv) < 3:
            print("❌ 请提供新版本号")
            return
        new_version = sys.argv[2]
        version_type = sys.argv[3] if len(sys.argv) > 3 else "patch"
        manager.update_version(new_version, version_type)
        
    elif command == "release":
        if len(sys.argv) < 3:
            print("❌ 请提供版本号")
            return
        version = sys.argv[2]
        notes = manager.generate_release_notes(version)
        print(f"版本 {version} 发布说明:")
        print("=" * 50)
        print(notes)
        
    else:
        print(f"❌ 未知命令: {command}")


if __name__ == "__main__":
    main()
