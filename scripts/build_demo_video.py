"""Build a subtitled MP4 from actual UI captures, source and study evidence.

No voice track; this is an edited demonstration, not a claimed live recording.
"""
import argparse
import hashlib
import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
WIDTH,HEIGHT,FPS,SECONDS=1920,1080,8,12
BG='#102323'; WHITE='#f1f6ef'; MUTED='#adc4ba'; ACCENT='#4fddba'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--font',default='C:/Windows/Fonts/msyh.ttc')
    args=parser.parse_args()
    font=lambda n:ImageFont.truetype(args.font,n)
    output=ROOT/'docs/demo'; output.mkdir(parents=True,exist_ok=True)
    temp=ROOT/'tmp/video';temp.mkdir(parents=True,exist_ok=True)
    study=json.loads((ROOT/'outputs/stage3_demo/study.json').read_text(encoding='utf-8'))
    slides=[]
    def base(title,chapter):
        im=Image.new('RGB',(WIDTH,HEIGHT),BG);d=ImageDraw.Draw(im)
        d.text((64,32),f'A-SHARE RESEARCH LAB  /  STAGE 03  /  {chapter:02d}',font=font(22),fill=ACCENT)
        d.text((64,78),title,font=font(48),fill=WHITE)
        d.line((64,154,1856,154),fill='#34554c',width=2)
        return im,d
    def body(d,lines,x=90,y=220,size=35,step=70):
        for line in lines:
            d.text((x,y),line,font=font(size),fill=WHITE);y+=step
    def ui(im,name):
        shot=Image.open(output/name).convert('RGB')
        shot.thumbnail((1320,770))
        im.paste(shot,(64,178))
    def add(im,caption):
        d=ImageDraw.Draw(im)
        d.rounded_rectangle((64,956,1856,1040),radius=12,fill='#28443d')
        d.text((90,978),caption,font=font(28),fill=WHITE)
        slides.append((im,caption))

    im,d=base('从量化因子到可复现的研究 Agent',1)
    body(d,['LangChain：类型化工具 + 可选模型客户端','LangGraph：必跑研究流程 + 有界工具循环',
            'FastAPI：后台实验、历史记录与报告下载','MCP：独立 stdio 工具入口，复用同一计算核心',
            '研究验证：walk-forward、参数敏感性、股票池与基准'],step=90)
    d.text((90,795),'人工演示数据 / 离线模式 / 无真实下单',font=font(32),fill=ACCENT)
    add(im,'这是可运行的工程项目；演示结果不能证明 A 股因子有效。')

    im,d=base('01 / 从页面提交一个有参数的实验',2);ui(im,'01-setup.png')
    body(d,['sample_stage3','12 股 / 182 日期','训练 60 日','测试 20 日','间隔 2 日','离线无需密钥'],x=1380,y=235,size=30,step=92)
    add(im,'本画面来自实际本地页面；点击开始研究，API 返回 ID，后台运行。')

    im,d=base('02 / 先有计算证据，再生成研究结论',3);ui(im,'02-result.png')
    body(d,['检查数据','计算因子','回测与成本','滚动验证','记录事件','下载报告'],x=1380,y=230,size=31,step=90)
    add(im,'收益由 Python 账本计算；模型只能解释证据，失败时明确回退。')

    im,d=base('03 / LangChain 在源码中真正参与调用',4)
    body(d,['# research_agent/langchain_runtime.py',
            'StructuredTool.from_function(..., args_schema=schema)',
            '# research_agent/tools.py',
            'self.langchain_tools()[name].invoke(arguments)',
            '# 可选模型：langchain.chat_models.init_chat_model',
            'self.chat_model.bind_tools(tools).invoke(messages)'],size=30,step=86)
    d.text((90,805),'LangGraph 管状态和循环；MCP 仍为独立入口。',font=font(33),fill=ACCENT)
    add(im,'这是实际实现路径，默认离线没有模型请求；外部模型效果尚未实测。')

    im,d=base('04 / 同期、同池比较样本外策略与基准',5)
    labels=['股票池','折数','样本外净收益','最大回撤','等权持有','收益差']
    xs=[95,390,590,940,1240,1560]
    for x,label in zip(xs,labels):d.text((x,230),label,font=font(29),fill=ACCENT)
    for i,p in enumerate(study['universes']):
        m,b=p['oos']['metrics'],p['benchmark']['metrics']
        row=[p['universe']['name'],str(len(p['folds'])),f"{m['total_return']:.2%}",f"{m['max_drawdown_daily']:.2%}",f"{b['total_return']:.2%}",f"{p['excess_total_return']:.2%}"]
        for x,v in zip(xs,row):d.text((x,340+i*110),v,font=font(35),fill=WHITE)
    body(d,['等权基准：首个样本外日开盘一次买入，100 股整手、相同佣金和滑点。',
            '期末盯市；没有卖出，所以不收卖出印花税。现金基准为零利息。',
            '默认股票池是文件内固定代码范围，不是官方历史指数成分。'],y=720,size=28,step=70)
    add(im,'保留实际负收益；策略与基准暴露不同，收益差不等于风险调整 alpha。')

    im,d=base('05 / 每一折都能找到当时的输入和参数',6);ui(im,'03-walk-forward.png')
    body(d,['先裁掉未来行情','训练含成本选参','间隔至少 2 日','后续测试不选参','现金持仓跨窗','不强制未来平仓'],x=1380,y=220,size=27,step=96)
    add(im,'逐折收益连乘对账至总样本外收益；测试尾段不足 4 日会排除。')

    im,d=base('06 / 切换股票池，检查稳健性而非挑赢家',7);ui(im,'04-pools.png')
    body(d,['all：文件内全池','sh_main：60 前缀','sz_main：深主板','可配静态自定义池','支持历史成员日期','来源须自行核实'],x=1380,y=220,size=26,step=96)
    add(im,'历史成员需要 known_at 与生效区间，程序不能认证成分来源。')

    im,d=base('07 / 分位与滑点敏感性：明确事后属性',8);ui(im,'05-sensitivity.png')
    body(d,['分位 0.1 / 0.2 / 0.5','滑点 0 / 5 / 10 bps','每池 9 组配置','同一测试区间','用于描述稳定性','不回写选参结果'],x=1380,y=230,size=26,step=92)
    add(im,'看到网格赢家后重选参数，再称它为样本外，会造成泄漏。')

    im,d=base('08 / Skill 指导方法，测试验证行为',9)
    body(d,['两个项目 Skill：','ashare-data-audit  → 数据、时点与股票池审计',
            'walk-forward-review  → 选参、基准和敏感性解读',
            '本地全新环境：47 项测试通过；pip check 通过',
            '关键反例：修改未来价格，过去选参和净值不变',
            '真实协议检查：LangChain HTTP stub + MCP stdio'],size=33,step=94)
    add(im,'浏览器还验证了实验提交、报告下载、历史重载与移动端布局。')

    im,d=base('09 / 交付、复现与诚实的边界',10)
    body(d,['python start_stage3.py              # 本地页面',
            'python start_stage3.py --study      # 研究报告',
            'Dockerfile + compose.yaml          # 容器定义',
            '.github/workflows/stage3.yml        # 自动测试与构建',
            '3 篇博客 + 源码 + 测试 + JSON/CSV/Markdown 报告',
            '当前机器无 Docker；CI 尚未推送运行。'],size=32,step=91)
    d.text((90,825),'下一步：核实真实数据、公司行动、历史成分，再做独立 holdout。',font=font(29),fill=ACCENT)
    add(im,'本视频为实际页面截图与证据剪辑，中文字幕，无旁白。')

    path=output/'stage3-demo.mp4'
    with imageio.get_writer(path,fps=FPS,codec='libx264',quality=8,macro_block_size=1,
                            ffmpeg_params=['-pix_fmt','yuv420p','-preset','fast','-movflags','+faststart']) as writer:
        for i,(im,caption) in enumerate(slides):
            im.save(temp/f'scene-{i+1:02d}.png')
            for second in range(SECONDS):
                frame=im.copy();d=ImageDraw.Draw(frame)
                end=64+int(1792*(i*SECONDS+second+1)/(len(slides)*SECONDS))
                d.rectangle((64,1054,end,1060),fill=ACCENT)
                data=np.asarray(frame)
                for _ in range(FPS):writer.append_data(data)
            print(f'Encoded chapter {i+1}/{len(slides)}',flush=True)
    def timestamp(seconds):return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02},000'
    subtitle='\n\n'.join(f'{i+1}\n{timestamp(i*SECONDS)} --> {timestamp((i+1)*SECONDS)}\n{caption}' for i,(_,caption) in enumerate(slides))+'\n'
    (output/'stage3-demo.srt').write_text(subtitle,encoding='utf-8')
    slides[4][0].save(output/'video-preview.png')
    with imageio.get_reader(path) as reader:
        metadata=reader.get_meta_data()
        assert abs(metadata['duration']-120)<.1
        assert metadata['size']==(WIDTH,HEIGHT)
        assert reader.count_frames()==len(slides)*SECONDS*FPS
    (output/'video_metadata.json').write_text(json.dumps({'duration_seconds':120,'fps':FPS,'size':[WIDTH,HEIGHT],
        'frames':960,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'method':'Actual local browser screenshots + source/research evidence edited with Chinese captions; silent'},indent=2),encoding='utf-8')
    print('Verified MP4:',path,flush=True)


if __name__=='__main__':main()
