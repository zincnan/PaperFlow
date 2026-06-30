AMC数据库比较稳定，似乎没有使用dblp那样的接口检索的必要。
检索关键词需要整理整合，以便适用于高级检索

普通行 = 正向关键词
空行分组 = 一个 OR 组
不同正向组之间 = AND
以 ! 开头的行 = NOT 关键词，全局排除
井号 # 开头 = 注释
@ 开头这一行是逻辑搜索字符串

python build_keywords.py -k keywords/test.txt