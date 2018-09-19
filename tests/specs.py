import os, sys
modulePath = os.path.abspath("../PdfSplitter")
if modulePath not in sys.path:
    sys.path.insert(0, modulePath)

from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfdevice import PDFDevice
from pdfminer.layout import LAParams, LTTextBox, LTTextLine
from pdfminer.converter import PDFPageAggregator
from PyPDF2 import PdfFileWriter, PdfFileReader
from ConfigEnv import Config
import unittest
import boto3
import json
import warnings
import io

from PdfSplitter import Splitter

class TestSplitter(unittest.TestCase):
    """docstring for TestSplitter."""

    def setUp(self):
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed.*<ssl.SSLSocket.*>")

        self._config = Config(self.getCurrentPath()+"data/testConfig.json")
        self._config.addFile = Config(self.getCurrentPath()+"data/splitterConfig.json")
        self._s3 = boto3.resource(
            's3',
            'eu-west-1',
            aws_access_key_id=self._config.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=self._config.get("AWS_SECRET_ACCESS_KEY"),
            aws_session_token= self._config.get("AWS_SESSION_TOKEN")
        )

        self._letterPath = self.getCurrentPath()+"data/pdf/letter.pdf";
        self._numberPath = self.getCurrentPath()+"data/pdf/number.pdf";

        self._bucket = self._s3.Bucket(self._config.get("AWS_S3_BUCKET"))

        # uplaod sur le bucket de données de test
        self._bucket.upload_file(self._letterPath, 'letter.pdf')
        self._bucket.upload_file(self._numberPath, 'number.pdf')

    def test__init__(self):
        splitter = Splitter(self.getCurrentPath()+"data/splitterConfig.json")
        for object in splitter._s3.Bucket(self._config.get("AWS_S3_BUCKET")).objects.all():
            self.assertEqual( object.bucket_name, self._config.get("AWS_S3_BUCKET") )

    def test__downloadAndCache(self):
        splitter = Splitter(self.getCurrentPath()+"data/splitterConfig.json")
        splitter._downloadAndCache("letter.pdf")
        with open(self._letterPath,"rb") as testFile :
            self.assertEqual( self.pdfToStr( splitter._cachePdf["letter.pdf"] ) , self.pdfToStr( testFile ) )

    def test__cachePdfOneFile(self):
        splitter = Splitter(self.getCurrentPath()+"data/splitterConfig.json")
        splitter._cachePdfOneFile("letter.pdf")
        writer = PdfFileWriter()
        writer.addPage(splitter._cachePage["letter.pdf"][1])
        writer.addPage(splitter._cachePage["letter.pdf"][2])

        outputWriteStream = io.BytesIO()
        writer.write(outputWriteStream)
        outputWriteStream.seek(0)
        self.assertEqual( self.pdfToStr( outputWriteStream ) , [ "b\n","c\n" ] )


    def test__getOnePage(self):
        splitter = Splitter(self.getCurrentPath()+"data/splitterConfig.json")
        page3 = splitter._getOnePage("letter.pdf",3)
        writer = PdfFileWriter()
        writer.addPage(page3)

        outputWriteStream = io.BytesIO()
        writer.write(outputWriteStream)
        outputWriteStream.seek(0)
        self.assertEqual( self.pdfToStr( outputWriteStream ) ,  [ "d\n" ] )

    def test__uploadToS3(self):
        splitter = Splitter(self.getCurrentPath()+"data/splitterConfig.json")
        page3 = splitter._getOnePage("letter.pdf",2)
        writer = PdfFileWriter()
        writer.addPage(page3)
        splitter._uploadToS3(writer,"output.pdf")

        outputWriteStream = io.BytesIO()
        self._bucket.download_fileobj("output.pdf",outputWriteStream)
        outputWriteStream.seek(0)
        self.assertEqual( self.pdfToStr( outputWriteStream ) , [ "c\n" ] )


    def test__splitOnePdf(self):
        splitter = Splitter(self.getCurrentPath()+"data/splitterConfig.json")
        with open(self.getCurrentPath()+"data/simpleTest.json") as data:
            data= json.load(data)
        splitter._splitOnePdf(data["input"], data["output"][0])

        outputWriteStream = io.BytesIO()
        self._bucket.download_fileobj("outputab01.pdf",outputWriteStream)
        outputWriteStream.seek(0)
        self.assertEqual( self.pdfToStr( outputWriteStream ) , [ "a\n","b\n","0\n","1\n" ] )

    def test_split(self):
        splitter = Splitter(self.getCurrentPath()+"data/splitterConfig.json")
        with open(self.getCurrentPath()+"data/simpleTest.json") as data:
            data= json.load(data)
        splitter.split(data)

        out1 = io.BytesIO()
        out2 = io.BytesIO()

        self._bucket.download_fileobj("outputab01.pdf",out1)
        self._bucket.download_fileobj("outputa0b1.pdf",out2)

        self.assertEqual( self.pdfToStr( out1 ) , [ "a\n","b\n","0\n","1\n" ] )
        self.assertEqual( self.pdfToStr( out2 ) , [ "a\n","0\n","b\n","1\n" ] )





    def getCurrentPath(self):
        return os.path.dirname(os.path.abspath(__file__))+"/"

    def pdfToStr(self,pdfBuffer):
        pages=[]
        parser = PDFParser(pdfBuffer)
        document = PDFDocument(parser)
        if not document.is_extractable:
            raise PDFTextExtractionNotAllowed
        rsrcmgr = PDFResourceManager()
        laparams = LAParams()
        device = PDFPageAggregator(rsrcmgr, laparams=laparams)
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        for page in PDFPage.create_pages(document):
            extracted_text = ""
            interpreter.process_page(page)
            layout = device.get_result()
            for lt_obj in layout:
                if isinstance(lt_obj, LTTextBox) or isinstance(lt_obj, LTTextLine):
                    extracted_text += lt_obj.get_text()
            pages.append(extracted_text)

        return(pages)
