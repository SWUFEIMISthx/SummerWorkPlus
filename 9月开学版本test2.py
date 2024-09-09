import csv
import json
import os
import re

import gradio as gr
import requests
from pdfplumber import open as pdf_open

# 创建下载存放文件夹-->当前文件夹下
# 定义全局变量 save_path 为你的默认下载路径
default_download_path = r"D:\暑期实训（雏鹰计划）\baocun"
save_path = default_download_path  # 可以在这里修改为其他路径，如果需要的话

if not os.path.exists(default_download_path):
    os.makedirs(default_download_path)

url_head = 'https://reportdocs.static.szse.cn'


def extract_and_save_text_from_pdf(pdf_path, output_dir, header_height=20):
    # 获取不带文件类型的文件名
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_path = os.path.join(output_dir, f'{base_name}.txt')

    with pdf_open(pdf_path) as pdf:
        pages = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                # 清理文本，保留必要的换行符，清理多余的空格和连续的换行符
                # 保留有意义的换行符（例如两行之间的换行），移除多余的空白行
                clean_text = re.sub(r'\n\s*\n', '\n\n', text)  # 合并连续的空白行
                clean_text = re.sub(r' +', ' ', clean_text)  # 清理多余的空格
                clean_text = clean_text.strip()  # 去除首尾空白
                pages.append(clean_text)

        # 将页面文本连接起来，并保留原有的换行符
        full_text = '\n'.join(pages)

        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_text)

    return output_path


def extract_and_save_questions_and_replies(filename, company_name, disclosure_time):
    # 初始化问题和回复列表
    questions = []
    answers = []

    # 读取文件
    with open(filename, 'r', encoding='utf-8') as file:
        content = file.read()

    # 使用负向前瞻来确保“问题”字样不跟在“参见”或“之”后面，并且确保“问题”后面跟的是编号格式
    pattern = r'''
    (请发行人.*?)                        # 匹配“请发行人”开头的问题部分
    \n*                                  # 可能存在的换行符
    (回复：|【回复】|【发行人.*?】|回复如下：|回复[:\s]+|【问题答复】)  # 匹配回复的开头
    (.*?)                                # 匹配回复内容
    (?![参见].+?问题)                     # 负向前瞻，确保“问题”不跟在“参见”后面
    (?![之].+?问题)                       # 新增负向前瞻，确保“问题”不跟在“之”后面
    (?=                                  # 前瞻断言，确保问题的结尾
        (请发行人|                   # 下一个问题以“请发行人”开头
        问题\s*(?:\d+(?:\.\d+)*)(?:\s*[\.\s、#]+(?:\d*\s*[\.\s、#]*)*)?|  # 匹配问题编号
        \Z)                              # 或者是文件的结尾
    )
    '''
    matches = re.findall(pattern, content, flags=re.DOTALL | re.VERBOSE)

    # 处理每一部分
    for index, match in enumerate(matches, start=1):
        question = match[0].strip()
        answer = match[2].strip()
        # 在标签后添加换行符
        questions.append(f"<Question{index}>\n{question}\n</Question{index}>\n\n")
        answers.append(f"<Answer{index}>\n{answer}\n</Answer{index}>\n\n")

    # 提取标题、公司名称、阶段、轮次、提问人类型和回复人类型
    title_text, stage, rounds, respondent_type, questioner_type, respondent_type_tag = extract_title_and_stage_and_rounds_and_respondent_type(
        filename, content)

    # 构建阶段标签
    stage_tag = f'<Stage>\n{stage}\n</Stage>\n\n' if stage else '<Stage>\n未指定阶段\n</Stage>\n\n'

    # 构建轮次标签
    rounds_tag = f'<Rounds>\n{rounds}\n</Rounds>\n\n'

    # 构建提问人类型标签
    questioner_type_tag = f'<Questioner Type>\n{questioner_type}\n</Questioner Type>\n\n'

    # 构建回复人类型标签
    respondent_type_tag = f'<Respondent Type>\n{" ".join(respondent_type) if respondent_type else "多方"}\n</Respondent Type>\n\n'

    # 构建输出内容
    output_content = f"<Title>\n{title_text}\n</Title>\n\n"
    output_content += f"<Company Name>\n{company_name}\n</Company Name>\n\n"
    output_content += f"<Announcement Date>\n{disclosure_time}\n</Announcement Date>\n\n"
    output_content += f"{stage_tag}{rounds_tag}{questioner_type_tag}{respondent_type_tag}"
    output_content += ''.join(questions + answers)

    # 保存到新文件
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(output_content)


def extract_title_and_stage_and_rounds_and_respondent_type(filename, content):
    # 使用 \n 分割内容并获取前六行
    lines = content.split('\n')[:6]
    # 将前六行合并成一段文本
    title_text = ' '.join(lines).strip()

    # 判断阶段
    stage = ""
    if "审核" in title_text:
        stage = "审核阶段"
    elif "注册" in title_text:
        stage = "注册阶段"

    # 判断轮次
    rounds = "不详"
    rounds_pattern = r'第(\d+)轮'
    rounds_match = re.search(rounds_pattern, title_text)
    if rounds_match:
        rounds = f"第{rounds_match.group(1)}轮"
    elif "首次" in title_text:
        rounds = "首次"

    # 判断回复人类型
    respondent_type = []
    if "法律" in filename or "律师事务所" in filename:
        respondent_type.append("律师")
    if "会计师" in filename:
        respondent_type.append("会计师")

    # 从正文中提取从“证券交易所：”出现到“请予审核。”截至的内容
    start_pattern = r'深圳证券交易所：'
    end_pattern = r'，请予审核。'
    start_match = re.search(start_pattern, content)
    end_match = re.search(end_pattern, content)
    if start_match and end_match:
        start_index = start_match.end()
        end_index = end_match.start()
        relevant_content = content[start_index:end_index].strip()

        # 在这段内容中查找关键词
        keywords = ["发行人", "律师", "会计师", "券商"]
        for keyword in keywords:
            if keyword in relevant_content and keyword not in respondent_type:
                respondent_type.append(keyword)

    # 构建阶段标签
    stage_tag = f'<Stage>\n{stage}\n</Stage>\n\n' if stage else '<Stage>\n未指定阶段\n</Stage>\n\n'

    # 构建轮次标签
    rounds_tag = f'<Rounds>\n{rounds}\n</Rounds>\n\n'

    # 构建回复人类型标签
    respondent_type_tag = f'<Respondent Type>\n{" ".join(respondent_type) if respondent_type else "多方"}\n</Respondent Type>\n\n'

    # 构建提问人类型标签
    questioner_type = "证券交易所"
    if len(respondent_type) == 1 and "律师" in respondent_type:
        questioner_type = "发行人"
    questioner_type_tag = f'<Questioner Type>\n{questioner_type}\n</Questioner Type>\n\n'

    return title_text, stage, rounds, respondent_type, questioner_type, respondent_type_tag


def process_company_data_szzs(company_name, save_path):
    # 主程序入口
    # 网页抓取部分
    generated_files = []  # 用于收集生成的文件路径

    # 确定保存路径
    if not save_path:  # 如果save_path为空字符串，则使用默认路径
        save_path = default_download_path

    # 创建以公司名称命名的新文件夹
    company_specific_path = os.path.join(save_path, company_name)
    if not os.path.exists(company_specific_path):
        os.makedirs(company_specific_path)

    for i in range(0, 500):
        url = f'https://listing.szse.cn/api/ras/infodisc/query?pageIndex={i}&pageSize=10&keywords=&disclosedStartDate=&disclosedEndDate=&catalog=4&bizType=1'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0'
        }
        response = requests.get(url=url, headers=headers)
        res = response.content
        res = res.decode('utf-8')
        res = json.loads(res)

        for item in res['data']:
            if item['cmpnm'] == company_name:  # 如果公司名称匹配
                company_name = item['cmpnm']
                disclosure_time = item['ddt']
                for pdf_item in item['subInfoDisclosureList']:
                    pdf_name = pdf_item['dfnm']
                    print(pdf_name)
                    pdf_url = url_head + pdf_item['dfpth']
                    response = requests.get(url=pdf_url, headers=headers)
                    if response.status_code == 200:
                        # 下载PDF文件到新的公司特定文件夹
                        pdf_file_path = os.path.join(company_specific_path, pdf_name)
                        with open(pdf_file_path, 'wb') as f:
                            f.write(response.content)
                        print("下载成功")
                        generated_files.append(pdf_file_path)  # 添加PDF文件路径

                        # 从PDF提取文本并保存到TXT文件
                        txt_file_path = extract_and_save_text_from_pdf(pdf_file_path, company_specific_path)
                        print("PDF文本内容提取并保存成功")
                        generated_files.append(txt_file_path)  # 添加TXT文件路径

                        # 对TXT文件进行处理
                        extract_and_save_questions_and_replies(txt_file_path, company_name, disclosure_time)
                        print("TXT文件处理完成")

                    else:
                        print("请求失败，状态码：", response.status_code)

    return generated_files, f"数据处理完成: {company_name}"


def process_company_data_sse(company_name):
    # 这里可以添加处理上交所数据的逻辑
    return [], f"数据处理完成 (上交所): {company_name}"


def display_files(exchange, company_name, save_path=default_download_path):
    if exchange == "深交所":
        files, message = process_company_data_szzs(company_name, save_path)
    elif exchange == "上交所":
        files, message = process_company_data_sse(company_name, save_path)

    # 构造一个字符串，列出所有文件的名称
    file_list = "\n".join([os.path.basename(f) for f in files])

    # 返回文件列表和消息
    return file_list, message, files


def extract_tags(file_path):
    """从文件中提取所有开头的标签，并保持它们的顺序"""
    tags = []
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        tag_pattern = re.compile(r'<[^/][^>]+>')  # 匹配开头的标签
        for match in tag_pattern.finditer(content):
            if match.group() not in tags:
                tags.append(match.group())
    return tags

# 修正：定义一个函数来提取标签和内容
def extract_tags_and_content(file_path):
    tags_content = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 使用正则表达式找到所有标签及其内容
    tag_pattern = re.compile(r'<([^>]+)>\n(.*?)\n</\1>', re.DOTALL)
    for match in tag_pattern.finditer(content):
        tag = match.group(1)
        content = match.group(2).strip()
        tags_content[tag] = content

    return tags_content

def show_tag_content(tag, file_path):
    """根据给定的标签显示对应的内容"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        start_tag = tag
        end_tag = f"</{tag[1:-1]}>"
        start_index = content.find(start_tag)
        end_index = content.find(end_tag, start_index) + len(end_tag)
        if start_index != -1 and end_index != -1:
            return content[start_index:end_index]
        else:
            return ""


# 假设您已经有了 get_answer_from_model 函数
def get_answer_from_model(question):
    # 加载模型并获取答案
    # 示例返回
    return "这是一个示例回答。"


# def load_files_for_company(folder):
#     # 使用全局变量 save_path
#     folder_path = os.path.join(save_path, folder)
#     if not os.path.exists(folder_path):
#         return []  # 如果路径不存在，返回空列表
#     files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]
#     return files
#
# def load_company_folders(save_path):
#     folders = [f for f in os.listdir(save_path) if os.path.isdir(os.path.join(save_path, f))]
#     return folders
#
# def load_tags_for_file(file, folder):
#     file_path = os.path.join(save_path, folder, file)
#     tags = extract_tags(file_path)
#     return tags
#
# def show_selected_tag_content(selected_tag, folder, file):
#     file_path = os.path.join(save_path, folder, file)
#     content = show_tag_content(selected_tag, file_path)
#     return content

# 修正：定义转换 TXT 到 CSV 的函数
def convert_txt_to_csv(txt_file_path, output_dir):
    # 构建 CSV 文件的路径
    csv_file_path = os.path.splitext(txt_file_path)[0] + '.csv'
    csv_file_path = os.path.join(output_dir, os.path.basename(csv_file_path))

    # 提取标签和内容
    tags_content = extract_tags_and_content(txt_file_path)

    # 写入 CSV 文件
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # 写入列名
        writer.writerow(tags_content.keys())
        # 写入内容
        writer.writerow(tags_content.values())

    return csv_file_path


# 创建 Blocks 应用
with gr.Blocks(theme=gr.themes.Soft(font=['Roboto', 'sans-serif'])) as demo:
    # 添加自定义 CSS
    gr.HTML("<style>h1 {font-size: 2em; color: #3f51b5; text-align: center; margin-top: 0;}</style>")

    # 添加标题
    gr.Markdown("# IPO问询与回复查询平台")

    with gr.Tab("一键爬取pdf和信息文档"):
        # 创建输入组件行
        with gr.Row():
            # 创建左侧列，包含下拉菜单和输入框
            with gr.Column(scale=1, variant='panel'):
                # 使用 gr.Row 和 variant='compact' 来控制组件的垂直居中
                with gr.Row(variant='compact'):
                    exchange_dropdown = gr.Dropdown(["深交所", "上交所"], label="选择证券交易所")
                with gr.Row(variant='compact'):
                    company_name_textbox = gr.Textbox(label="输入目标公司名称")
                with gr.Row(variant='compact'):
                    save_path_textbox = gr.Textbox(label="自定义保存路径",
                                                   placeholder=r"可留空，留空则使用默认路径:D:\\暑期实训（雏鹰计划）\\baocun")
                # 创建提交按钮，并使用 gr.Row 控制垂直居中
                with gr.Row(variant='compact'):
                    submit_button = gr.Button("开始爬取并提取信息")
                # 添加 Clear 按钮
                clear_button = gr.Button("Clear", variant="secondary")

            # 创建右侧列，包含输出组件
            with gr.Column(scale=2):
                # 创建输出组件
                file_list_textarea = gr.TextArea(label="已获得的文件列表")
                file_dropdown = gr.Dropdown([], label="选择提取信息后的文件")
                tag_dropdown = gr.Dropdown([], label="选择标签")
                tag_content_area = gr.TextArea(label="标签内容")
                status_message_html = gr.HTML(label="状态消息")
                # 新增：添加转换为 CSV 的按钮
                convert_csv_button = gr.Button("转换为CSV文件")


        # 定义一个变量来存储所有文件路径
        all_files = gr.State([])

        def on_submit(save_path, exchange, company_name):
            # 检查用户是否提供了保存路径
            if not save_path.strip():
                save_path = default_download_path  # 使用默认路径
                message = f"未指定保存路径，使用默认路径: <code>{default_download_path}</code>"
            else:
                message = f"文件将保存在: <code>{save_path}</code>"

            # 调用 display_files 函数获取所有文件路径
            file_list, additional_message, files = display_files(exchange, company_name, save_path)

            # 更新文件列表、状态消息和下拉框
            txt_files = [f for f in files if f.endswith('.txt')]  # 仅保留 .txt 文件
            file_names = [os.path.basename(f) + " (已提取标签信息)" for f in txt_files]
            return file_list, gr.update(choices=file_names), gr.update(value=None), gr.update(
                value=None), message + "<br>" + additional_message, txt_files

        def update_tags(selected_file, all_files):
            selected_file_path = None
            for file_path in all_files:
                base_name = os.path.basename(file_path) + " (已提取标签信息)"
                if base_name == selected_file:
                    selected_file_path = file_path
                    break

            if selected_file_path:
                tags = extract_tags(selected_file_path)
                return gr.update(choices=tags), gr.update(value=None)
            else:
                return gr.update(choices=[]), gr.update(value=None)

        def show_selected_tag_content(selected_tag, selected_file, all_files):
            selected_file_path = None
            for file_path in all_files:
                base_name = os.path.basename(file_path) + " (已提取标签信息)"
                if base_name == selected_file:
                    selected_file_path = file_path
                    break

            if selected_file_path:
                content = show_tag_content(selected_tag, selected_file_path)
                return content
            else:
                return "无法找到文件或标签内容。"

            # 新增：定义一个事件处理器来处理转换操作
        def on_convert_to_csv(all_files):
            # 过滤出所有的 TXT 文件
            txt_files = [file for file in all_files if file.endswith('.txt')]
            # 调用转换函数
            csv_files = [convert_txt_to_csv(file, os.path.dirname(file)) for file in txt_files]
            return '\n'.join(os.path.basename(f) for f in csv_files), "转换完成"

        # 绑定按钮的事件处理器
        convert_csv_button.click(on_convert_to_csv, inputs=[all_files],
                                     outputs=[file_list_textarea, status_message_html])


        # 绑定事件处理器
        submit_button.click(on_submit, [save_path_textbox, exchange_dropdown, company_name_textbox],
                            [file_list_textarea, file_dropdown, tag_dropdown, tag_content_area, status_message_html,
                             all_files])
        file_dropdown.change(update_tags, [file_dropdown, all_files], [tag_dropdown, tag_content_area])
        tag_dropdown.change(show_selected_tag_content, [tag_dropdown, file_dropdown, all_files], tag_content_area)

        # 清除所有组件的内容
        def clear_all():
            return (
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=None),
                gr.update(value=None),
                gr.update(value=None),
                gr.update(value=""),
                gr.update(value=None),
                gr.update(value=None),
                gr.update(value=None),
                gr.update(value=""),
                gr.update(value=None)
            )

        # 绑定 Clear 按钮的事件处理器
        clear_button.click(clear_all, outputs=[
            exchange_dropdown,
            company_name_textbox,
            save_path_textbox,
            file_list_textarea,
            file_dropdown,
            tag_dropdown,
            tag_content_area,
            status_message_html,
            all_files
        ])

    with gr.Tab("浏览已保存的文件"):
        # 创建输入组件行
        with gr.Row():
            # 创建左侧列，包含下拉菜单和输入框
            with gr.Column(scale=1, variant='panel'):
                with gr.Row(variant='compact'):
                    company_dropdown = gr.Dropdown([], label="选择公司")
                with gr.Row(variant='compact'):
                    file_dropdown_browse = gr.Dropdown([], label="选择文件")
                with gr.Row(variant='compact'):
                    tag_dropdown_browse = gr.Dropdown([], label="选择标签")
                with gr.Row(variant='compact'):
                    browse_button = gr.Button("刷新")

            # 创建右侧列，包含输出组件
            with gr.Column(scale=2):
                tag_content_area_browse = gr.TextArea(label="标签内容")

        # 定义一个变量来存储所有公司文件夹路径
        all_companies = gr.State([])

        def list_companies(save_path):
            if not save_path.strip():
                save_path = default_download_path  # 使用默认路径
            if not os.path.exists(save_path):
                return gr.update(choices=[]), "保存路径不存在。"
            companies = [d for d in os.listdir(save_path) if os.path.isdir(os.path.join(save_path, d))]
            if not companies:
                return gr.update(choices=[]), "未找到任何公司文件夹。"
            return gr.update(choices=companies), "公司列表已更新。"

        def list_files(selected_company, save_path):
            if not save_path.strip():
                save_path = default_download_path  # 使用默认路径
            company_path = os.path.join(save_path, selected_company)
            if not os.path.exists(company_path):
                return gr.update(choices=[]), "公司文件夹不存在。"
            files = [f for f in os.listdir(company_path) if f.endswith('.txt')]
            if not files:
                return gr.update(choices=[]), "未找到任何txt文件。"
            return gr.update(choices=files), "文件列表已更新。"

        def update_tags_browse(selected_file, selected_company, save_path):
            if not save_path.strip():
                save_path = default_download_path  # 使用默认路径
            file_path = os.path.join(save_path, selected_company, selected_file)
            if not os.path.exists(file_path):
                return gr.update(choices=[]), "文件不存在。"
            tags = extract_tags(file_path)
            if not tags:
                return gr.update(choices=[]), "未找到任何标签。"
            return gr.update(choices=tags), "标签列表已更新。"

        def show_selected_tag_content_browse(selected_tag, selected_file, selected_company, save_path):
            if not save_path.strip():
                save_path = default_download_path  # 使用默认路径
            file_path = os.path.join(save_path, selected_company, selected_file)
            if not os.path.exists(file_path):
                return "文件不存在。"
            content = show_tag_content(selected_tag, file_path)
            if not content:
                return "标签内容未找到。"
            return content

        # 绑定事件处理器

        # 绑定“刷新”按钮，点击后列出公司
        browse_button.click(
            list_companies,
            inputs=save_path_textbox,
            outputs=[company_dropdown, tag_content_area_browse]  # 也可以返回一个状态消息
        )

        # 当选择公司时，更新文件下拉框
        company_dropdown.change(
            list_files,
            inputs=[company_dropdown, save_path_textbox],
            outputs=[file_dropdown_browse, tag_content_area_browse]  # 也可以返回一个状态消息
        )

        # 当选择文件时，更新标签下拉框
        file_dropdown_browse.change(
            update_tags_browse,
            inputs=[file_dropdown_browse, company_dropdown, save_path_textbox],
            outputs=[tag_dropdown_browse, tag_content_area_browse]  # 也可以返回一个状态消息
        )

        # 当选择标签时，显示标签内容
        tag_dropdown_browse.change(
            show_selected_tag_content_browse,
            inputs=[tag_dropdown_browse, file_dropdown_browse, company_dropdown, save_path_textbox],
            outputs=tag_content_area_browse
        )

    with gr.Tab("与大模型交互(测试中)"):
        with gr.Row():
            question_input = gr.Textbox(label="输入您的问题")
            answer_output = gr.Textbox(label="答案")
        # 创建一个按钮来触发问答
        qa_button = gr.Button("询问")

        def qa_handler(question):
            answer = get_answer_from_model(question)
            return answer

        # 绑定问答按钮的事件处理器
        qa_button.click(qa_handler, inputs=[question_input], outputs=[answer_output])

    # 启动 Gradio 应用
    demo.launch()  # 设置 share=True 以便创建公共链接（如需要）
