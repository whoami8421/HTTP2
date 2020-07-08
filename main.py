from spider import H2Spider
import requests
import time
import threading
import random

URL = [
    'https://www.ustc.edu.cn',
    'https://www.cnblogs.com/',
    'https://www.qq.com/',
    'https://www.zhihu.com/',
    'https://blog.csdn.net/danscort2000/article/details/82107568',
    'https://blog.csdn.net/helloexp/article/details/103280584'
]
def test1():
    # 完整性测试
    doc_url = 'https://www.taobao.com/'
    pic_url = 'https://aecpm.alicdn.com/simba/img/TB1JNHwKFXXXXafXVXXSutbFXXX.jpg'
    spider = H2Spider()
    doc_spider = spider.get(doc_url)
    pic_spider = spider.get(pic_url)
    with open('./test/doc_spider.html', 'wb') as fp:
        fp.write(doc_spider.content)
    with open('./test/pic_spider.png', 'wb') as fp:
        fp.write(pic_spider.content)

    doc_request = requests.get(doc_url)
    pic_request = requests.get(pic_url)
    with open('./test/doc_request.html', 'wb') as fp:
        fp.write(doc_request.content)
    with open('./test/pic_request.png', 'wb') as fp:
        fp.write(pic_request.content)

def test2():
    # 固定请求测试
    spider = H2Spider()
    url = 'https://www.taobao.com/'
    t1 = time.time()
    spider.get(url)
    t2 = time.time()
    t_s_1 = t2 - t1
    t1 = time.time()
    requests.get(url)
    t2 = time.time()
    t_r_1 = t2 - t1
    with open('./test/固定1.txt','w') as fp:
        fp.write('spider: %s , request: %s' % (t_s_1, t_r_1))
    # print('ts1: %s, tr1: %s' % (t_s_1, t_r_1))

    spider = H2Spider()
    count = 10
    t1 = time.time()
    for i in range(count):
        print(i)
        spider.get(url)
    t2 = time.time()
    t_s_10 = t2 - t1
    t1 = time.time()
    for i in range(count):
        print(i)
        requests.get(url)
    t2 = time.time()
    t_r_10 = t2 - t1
    # print('ts10: %s, tr10: %s' % (t_s_10, t_r_10))
    spider = H2Spider()

    count = 100
    t1 = time.time()
    for i in range(count):

        res = spider.get(url)
        print('spider: %s, headers: %s' % (i, res.headers))
    t2 = time.time()
    t_s_100 = t2 - t1
    t1 = time.time()
    for i in range(count):
        res = requests.get(url)
        print('requests: %s, headers: %s' % (i, res.headers))
    t2 = time.time()
    t_r_100 = t2 - t1

    spider = H2Spider()
    count = 1000
    t1 = time.time()
    for i in range(count):
        res = spider.get(url)
        print('spider: %s, headers: %s' % (i, res.headers))
    t2 = time.time()
    t_s_1000 = t2 - t1

    result = 'spider: %s, %s, %s, %s\nrequest: %s, %s, %s, ' % (t_s_1,
                                                                  t_s_10,
                                                                  t_s_100,
                                                                  t_s_1000,
                                                                  t_r_1,
                                                                  t_r_10,
                                                                  t_r_100,
                                                                  )
    with open('./test/固定.txt', 'w') as fp:
        fp.write(result)

    t1 = time.time()
    for i in range(count):
        print(i)
        requests.get(url)
    t2 = time.time()
    t_r_1000 = t2 - t1
    #
    # # count = 10000
    # # t1 = time.time()
    # # for i in range(count):
    # #     print(i)
    # #     spider.get(url)
    # # t2 = time.time()
    # # t_s_10000 = t2 - t1
    # # t1 = time.time()
    # # for i in range(count):
    # #     print(i)
    # #     requests.get(url)
    # # t2 = time.time()
    # # t_r_10000 = t2 - t1
    with open('./test/固定.txt','a+') as fp:
        fp.write('%s' % t_r_1000)


def test3():
    r1 = random.choice(URL)
    r10 = []
    r100 = []
    r1000 = []
    h1headers = {
        'accept-encoding': 'gzip, deflate',
        'connection': 'close',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88'
    }

    for i in range(10):
        r10.append(random.choice(URL))

    for i in range(100):
        r100.append(random.choice(URL))

    for i in range(1000):
        r1000.append(random.choice(URL))

    spider = H2Spider()
    t1 = time.time()
    spider.get(r1)
    t2 = time.time()
    ts1 = t2 - t1
    t1 = time.time()
    requests.get(r1)
    t2 = time.time()
    tr1 = t2 - t1
    with open('./test/随机.txt', 'w') as fp:
        fp.write('ts1: %s, tr1: %s\n' % (ts1, tr1))

    spider = H2Spider()
    t1 = time.time()
    for i in range(10):
        res = spider.get(r10[i])
        print('spider: %s, headers: %s' % (i, res.headers))
    t2 = time.time()
    ts10 = t2 - t1
    t1 = time.time()
    for i in range(10):
        res = requests.get(r10[i],h1headers)
        print('requests: %s, headers: %s' % (i, res.headers))
    t2 = time.time()
    tr10 = t2 - t1
    with open('./test/随机.txt', 'a') as fp:
        fp.write('ts10: %s, tr10: %s\n' % (ts10, tr10))

    spider = H2Spider()
    t1 = time.time()
    for i in range(100):
        res = spider.get(r100[i])
        print('spider: %s, headers: %s' % (i, res.headers))
    t2 = time.time()
    ts100 = t2 - t1
    t1 = time.time()
    for i in range(100):
        res = requests.get(r100[i],h1headers)
        print('requests: %s, headers: %s' % (i, res.headers))
    t2 = time.time()
    tr100 = t2 - t1
    with open('./test/随机.txt', 'a') as fp:
        fp.write('ts100: %s, tr100: %s\n' % (ts100, tr100))

    spider = H2Spider()
    t1 = time.time()
    for i in range(1000):
        res = spider.get(r1000[i])
        print('spider: %s, headers: %s' % (i, res.headers))
    t2 = time.time()
    ts1000 = t2 - t1
    with open('./test/随机.txt', 'a') as fp:
        fp.write('ts1000: %s, ' % (ts1000))
    # t1 = time.time()
    # for i in range(1000):
    #     res = requests.get(r1000[i])
    #     print('requests: %s, headers: %s' % (i, res.headers))
    # t2 = time.time()
    # tr1000 = t2 - t1
    # with open('./test/随机.txt', 'a') as fp:
    #     fp.write('tr1000: %s\n' % (tr1000))
    #

import socket
if __name__ == '__main__':
    spider = H2Spider()
    res = spider.get('https://www.taobao.com')
    print(res.headers)
    print(res.text)
    # test1()
    #s = socket.create_connection(('www.zhihu.com', 443))

