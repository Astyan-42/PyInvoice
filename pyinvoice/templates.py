from __future__ import unicode_literals
from datetime import datetime, date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer

from pyinvoice.components import SimpleTable, TableWithHeader, PaidStamp
from pyinvoice.models import PDFInfo, Item, Transaction, InvoiceInfo, ServiceProviderInfo, ClientInfo


class SimpleInvoice(SimpleDocTemplate):
    default_pdf_info = PDFInfo(title='Invoice', author='CiCiApp.com', subject='Invoice')

    def __init__(self, invoice_path, pdf_info=None):
        if not pdf_info:
            pdf_info = self.default_pdf_info

        SimpleDocTemplate.__init__(
            self,
            invoice_path,
            pagesize=letter,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
            **pdf_info.__dict__
        )

        self._defined_styles = getSampleStyleSheet()
        self._defined_styles.add(
            ParagraphStyle('RightHeading1', parent=self._defined_styles.get('Heading1'), alignment=TA_RIGHT)
        )
        self._defined_styles.add(
            ParagraphStyle('TableParagraph', parent=self._defined_styles.get('Normal'), alignment=TA_CENTER)
        )

        self.invoice_info = None
        self.service_provider_info = None
        self.client_info = None
        self.is_paid = False
        self._items = []
        self._item_tax_rate = None
        self._transactions = []
        self._story = []
        self._bottom_tip = None
        self._bottom_tip_align = None

    @property
    def items(self):
        return self._items[:]

    def add_item(self, item):
        if isinstance(item, Item):
            self._items.append(item)

    def set_item_tax_rate(self, rate):
        self._item_tax_rate = rate

    @property
    def transactions(self):
        return self._transactions[:]

    def add_transaction(self, t):
        if isinstance(t, Transaction):
            self._transactions.append(t)

    def set_bottom_tip(self, text, align=TA_CENTER):
        self._bottom_tip = text
        self._bottom_tip_align = align

    @staticmethod
    def __format_value(value):
        if isinstance(value, datetime):
            value = value.strftime('%Y-%m-%d %H:%M')
        elif isinstance(value, date):
            value = value.strftime('%Y-%m-%d')
        return value

    def __attribute_to_table_data(self, instance, attribute_verbose_name_list):
        data = []

        for property_name, verbose_name in attribute_verbose_name_list:
            attr = getattr(instance, property_name)
            if attr:
                attr = self.__format_value(attr)
                data.append(['{0}:'.format(verbose_name), attr])

        return data

    def __build_invoice_info(self):
        if isinstance(self.invoice_info, InvoiceInfo):
            self._story.append(
                Paragraph('Invoice', self._defined_styles.get('RightHeading1'))
            )

            props = [('invoice_id', 'Invoice id'), ('invoice_datetime', 'Invoice date'),
                     ('due_datetime', 'Invoice due date')]

            self._story.append(
                SimpleTable(self.__attribute_to_table_data(self.invoice_info, props), horizontal_align='RIGHT')
            )

    def __service_provider_data(self):
        props = [('name', 'Name'), ('street', 'Street'), ('city', 'City'), ('state', 'State'),
                 ('country', 'Country'), ('post_code', 'Post code'), ('vat_tax_number', 'Vat/Tax number')]

        return self.__attribute_to_table_data(self.service_provider_info, props)

    def __build_service_provider_info(self):
        # Merchant
        if isinstance(self.service_provider_info, ServiceProviderInfo):
            self._story.append(
                Paragraph('Merchant', self._defined_styles.get('RightHeading1'))
            )

            self._story.append(
                SimpleTable(self.__service_provider_data(), horizontal_align='RIGHT')
            )

    def __client_info_data(self):
        props = [('name', 'Name'), ('street', 'Street'), ('city', 'City'), ('state', 'State'),
                 ('country', 'Country'), ('post_code', 'Post code'), ('email', 'Email'), ('client_id', 'Client id')]
        return self.__attribute_to_table_data(self.client_info, props)

    def __build_client_info(self):
        # ClientInfo
        if isinstance(self.client_info, ClientInfo):
            self._story.append(
                Paragraph('Client', self._defined_styles.get('Heading1'))
            )

            self._story.append(
                SimpleTable(self.__client_info_data(), horizontal_align='LEFT')
            )

    def __build_service_provider_and_client_info(self):
        if isinstance(self.service_provider_info, ServiceProviderInfo) and isinstance(self.client_info, ClientInfo):
            # Merge Table
            table_data = [
                [Paragraph('Service Provider', self._defined_styles.get('Heading1')), '', '', Paragraph('Client', self._defined_styles.get('Heading1')), '']
            ]
            table_style = [
                ('SPAN', (0, 0), (1, 0)),
                ('SPAN', (3, 0), (4, 0)),
                ('LINEBELOW', (0, 0), (1, 0), 1, colors.gray),
                ('LINEBELOW', (3, 0), (4, 0), 1, colors.gray),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ]
            client_info_data = self.__client_info_data()
            service_provider_data = self.__service_provider_data()
            diff = abs(len(client_info_data) - len(service_provider_data))
            if diff > 0:
                if len(client_info_data) < len(service_provider_data):
                    client_info_data.extend([["", ""]]*diff)
                else:
                    service_provider_data.extend([["", ""]*diff])
            for d in zip(service_provider_data, client_info_data):
                d[0].append('')
                d[0].extend(d[1])
                table_data.append(d[0])
            self._story.append(
                Table(table_data, style=table_style)
            )
        else:
            self.__build_service_provider_info()
            self.__build_client_info()

    def __build_items(self):
        # Items
        item_data = []
        item_subtotal = 0

        for item in self._items:
            if not isinstance(item, Item):
                continue

            item_data.append(
                (
                    item.name,
                    Paragraph(item.description, self._defined_styles.get('TableParagraph')),
                    item.units,
                    item.unit_price,
                    item.amount
                )
            )
            item_subtotal += item.amount

        if item_data:
            self._story.append(
                Paragraph('Detail', self._defined_styles.get('Heading1'))
            )

            item_data_title = ('Name', 'Description', 'Units', 'Unit Price', 'Amount')
            item_data.insert(0, item_data_title)  # Insert title

            # Summary field
            sum_start_y_index = len(item_data)
            sum_end_x_index = -1 - 1
            sum_start_x_index = len(item_data_title) - abs(sum_end_x_index)
            style = []

            # ##### Subtotal #####
            item_data.append(
                ('Subtotal', '', '', '', item_subtotal)
            )

            style.append(('SPAN', (0, sum_start_y_index), (sum_start_x_index, sum_start_y_index)))
            style.append(('ALIGN', (0, sum_start_y_index), (sum_end_x_index, -1), 'RIGHT'))

            # Tax total
            if self._item_tax_rate is not None:
                tax_total = item_subtotal * (Decimal(str(self._item_tax_rate)) / Decimal('100'))
                item_data.append(
                    ('Vat/Tax ({0}%)'.format(self._item_tax_rate), '', '', '', tax_total)
                )
                sum_start_y_index += 1
                style.append(('SPAN', (0, sum_start_y_index), (sum_start_x_index, sum_start_y_index)))
                style.append(('ALIGN', (0, sum_start_y_index), (sum_end_x_index, -1), 'RIGHT'))
            else:
                tax_total = None

            # Total
            total = item_subtotal + tax_total if tax_total else Decimal('0')
            item_data.append(('Total', '', '', '', total))
            sum_start_y_index += 1
            style.append(('SPAN', (0, sum_start_y_index), (sum_start_x_index, sum_start_y_index)))
            style.append(('ALIGN', (0, sum_start_y_index), (sum_end_x_index, -1), 'RIGHT'))

            self._story.append(TableWithHeader(item_data, horizontal_align='LEFT', style=style))

    def __build_transactions(self):
        # Transaction
        transaction_table_data = [
            (
                t.transaction_id,
                Paragraph(t.gateway, self._defined_styles.get('TableParagraph')),
                self.__format_value(t.transaction_datetime),
                t.amount,
            ) for t in self._transactions if isinstance(t, Transaction)
        ]

        if transaction_table_data:
            self._story.append(
                Paragraph('Transaction', self._defined_styles.get('Heading1'))
            )
            transaction_table_data.insert(0, ('Transaction id', 'Gateway', 'Transaction date', 'Amount'))
            self._story.append(TableWithHeader(transaction_table_data, horizontal_align='LEFT'))

    def __build_bottom_tip(self):
        if self._bottom_tip:
            self._story.append(Spacer(5, 5))
            self._story.append(
                Paragraph(
                    self._bottom_tip,
                    ParagraphStyle(
                        'BottomTip',
                        parent=self._defined_styles.get('Normal'),
                        alignment=self._bottom_tip_align
                    )
                )
            )

    def finish(self):
        self._story = []

        self.__build_invoice_info()
        self.__build_service_provider_and_client_info()
        self.__build_items()
        self.__build_transactions()
        self.__build_bottom_tip()

        self.build(self._story, onFirstPage=PaidStamp(7 * inch, 5.8 * inch) if self.is_paid else None)