import requests
import json

from flask import Flask, render_template, request, redirect, make_response

from peewee import SqliteDatabase, fn

from models import Customer, Invoice, InvoiceItem

from weasyprint import HTML

app = Flask(__name__)

db = SqliteDatabase("invoices.db")
db.create_tables([Customer, Invoice, InvoiceItem])


@app.route("/")
def index():
    total_customers = Customer.select().count()  # Count total customers
    top_items = (InvoiceItem
                 .select(InvoiceItem.item_name, fn.SUM(InvoiceItem.qty).alias('total_qty'))
                 .group_by(InvoiceItem.item_name)
                 .order_by(fn.SUM(InvoiceItem.qty).desc())
                 .limit(3))  # Get top 3 items

    return render_template("index.html", total_customers=total_customers, top_items=top_items)



@app.route("/new-customer")
def create_customer_form():
    return render_template("create-customer.html")

@app.route("/customers", methods=["POST", "GET"])
def customers():
    if request.method == "POST":
        action = request.form.get("action")  # Check if delete action is triggered

        if action == "delete":
            customer_id = request.form.get("customer_id")
            try:
                customer = Customer.get_by_id(customer_id)
                customer.delete_instance()  # Delete the customer from the database
                return redirect("/customers")
            except Customer.DoesNotExist:
                return "Error: Customer does not exist", 400  # Handle invalid ID
        
        elif action == "update":
            customer_id = request.form.get("customer_id")
            full_name = request.form.get("full_name")
            address = request.form.get("address")

            try:
                customer = Customer.get_by_id(customer_id)
                customer.full_name = full_name
                customer.address = address
                customer.save()
                return redirect("/customers")
            except Customer.DoesNotExist:
                return "Error: Customer does not exist", 400

        # If it's not delete, it's a new customer creation
        full_name = request.form.get("full_name")
        address = request.form.get("address")
        customer = Customer(full_name=full_name, address=address)
        customer.save()
        return redirect("/customers")

    # Render customer list
    customers = Customer.select()
    return render_template("list-customer.html", customers=customers)



# @app.route("/new-invoice")
# def create_invoice_form():
#     return render_template("create-invoice.html")

@app.route("/new-invoice/<int:customer_id>")
def create_invoice_form(customer_id):
    customer = Customer.get_by_id(customer_id)  
    return render_template("create-invoice.html", customer=customer)

@app.route("/invoices", methods=["GET", "POST"])
def invoices():
    if request.method == "POST":
        data = request.form
        
        if data.get("action") == "delete":
            invoice_id = data.get("invoice_id")

            invoice = Invoice.get_or_none(Invoice.invoice_id == invoice_id)
            if invoice:
                invoice.delete_instance()  # Delete invoice
            return redirect("/invoices")  # ✅ Correctly indented

        total_amount = float(data.get("total_amount"))
        tax_percent = float(data.get("tax_percent"))

        items_json = data.get("invoice_items")
        items = json.loads(items_json)

        # ✅ Ensure the invoice is saved before accessing its invoice_id
        invoice = Invoice.create(
            customer=data.get("customer_id"),
            customer_name=data.get("customer_name"),
            date=data.get("date"),
            total_amount=total_amount,
            tax_percent=tax_percent,
            payable_amount=total_amount + (total_amount * tax_percent) / 100,
        )

        api_url = "https://frappe.school/api/method/generate-pro-einvoice-id"
        payload = {
            "customer_name": invoice.customer_name,
            "invoice_id": invoice.invoice_id,  # ✅ Will exist because invoice is created first
            "payable_amount": invoice.payable_amount
        }

        try:
            response = requests.post(api_url, json=payload)
            response_data = response.json()

            if "arn" in response_data:
                invoice.arn = response_data["arn"]
                invoice.save()
            else:
                print("Failed to generate ARN:", response_data)

        except requests.RequestException as e:
            print("Error connecting to e-Invoicing API:", e)
        
        for item in items:
            InvoiceItem.create(
                invoice=invoice,
                item_name=item.get("item_name"),
                qty=item.get("qty"),
                rate=item.get("price"),
                amount=int(item.get("qty")) * float(item.get("price")),
            )

        return redirect("/invoices")

    else:
        return render_template("list-invoice.html", invoices=Invoice.select())



@app.route("/download/<int:invoice_id>")
def download_pdf(invoice_id):
    # get the invoice
    invoice = Invoice.get_by_id(invoice_id)

    # Generate the PDF
    html = HTML(string=render_template("print/invoice.html", invoice=invoice))
    response = make_response(html.write_pdf())

    # Set headers for PDF download
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="invoice_{invoice_id}.pdf"'

    return response

    