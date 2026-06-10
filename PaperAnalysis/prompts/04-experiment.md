## 实验环境与工作目录规范

本项目目录被指定为实验的唯一工作目录。所有由人工或智能体执行的实验操作，都必须严格限制在当前项目目录内完成，避免污染系统环境、其他项目目录或用户主目录。

一定要遵守
### 环境要求

实验环境必须基于已有的 Conda 环境 py312 创建本地虚拟环境 venv，venv位于项目根目录下，如果论文需要的实验环境与要求不符合，请终止并告诉我，以便我重新设定并创建实验环境

所有 Python 代码、脚本、实验任务、依赖安装和调试过程，都必须使用当前项目目录下的本地虚拟环境：

./venv/bin/python

不得直接使用系统 Python，不得直接使用全局 Conda Python，也不得将依赖安装到系统环境或其他项目环境中。

推荐初始化方式如下：

conda activate py312
python -m venv venv
./venv/bin/python -m ensurepip --upgrade
./venv/bin/python -m pip install --upgrade pip setuptools wheel

使用环境前应确认 Python 路径：

./venv/bin/python --version
./venv/bin/python -m pip --version

安装依赖时必须使用：

./venv/bin/python -m pip install <package>

禁止使用以下形式，除非已经明确确认其指向当前项目的 venv：

pip install <package>
python script.py


### 数据存储和处理要求
所有实验数据、要下载的东西，中间数据、模型权重、日志文件、缓存文件、评估结果、图表、表格和实验过程文件，都必须存储在当前项目目录下，可以用适当的目录分类存储

.
├── README.md 
├── venv/
├── outputs/ 
│   ├── logs/ 
│   ├── figures/ 
│   └── tables/

不得将实验相关文件写入以下位置：
~
/tmp
/var/tmp
其他项目目录
系统级目录
未明确指定的外部路径



## Agent实验确认规则

大规模的实验任务，需要和用户讨论试验计划后，经确认再执行，不允许自动执行后台大规模实验任务，否则既耗时，也有可能不是我需要的实验。除了启动实验以外的所有权限，都给你，但要遵守本实验要求。


### 其他要求
1. 除了git clone来的代码自带了git管理以外，整个项目不引入git，不要对整个项目进行git初始化