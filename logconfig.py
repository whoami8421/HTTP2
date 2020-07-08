import logging

formatter = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(filename='./spider.log',
                    level=logging.INFO,
                    format=formatter,
                    filemode='w',
                    )
