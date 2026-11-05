"""Generate fictional sample rental agreements (PDF) used for the demo and the eval set.

    python samples/make_samples.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

HERE = Path(__file__).parent

PARTIES = (
    "This Rental Agreement is made at Bengaluru on 1st November 2026 between Mr. Suresh Rao, "
    "PAN ABCDE1234F, phone +91 98450 12345, email suresh.rao@example.com (hereinafter the \"OWNER\") "
    "and Ms. Neha Kulkarni, phone 9876543210 (hereinafter the \"TENANT\"). All names and details in this "
    "document are fictional and for demonstration only."
)
PREMISES = ("1. Premises: The Owner lets out the residential flat No. 304, Green Meadows Apartments, "
            "12th Main, Sample Layout, Bengaluru 560000, together with fittings listed in Annexure A.")

SAMPLES = {
    "fair-agreement": [
        PREMISES,
        "2. Term: This agreement is for a period of eleven (11) months commencing from 1st December 2026.",
        "3. Rent: The monthly rent is Rs. 30,000 (Rupees Thirty Thousand only), payable on or before the "
        "5th day of every month by bank transfer.",
        "4. Security Deposit: The Tenant has paid a refundable, interest-free security deposit of Rs. 60,000 "
        "(Rupees Sixty Thousand only). The deposit shall be refunded within 15 days of the Tenant handing over "
        "vacant possession, after deducting only unpaid rent, unpaid utility bills and the reasonable cost of "
        "damage beyond normal wear and tear, with receipts shared with the Tenant.",
        "5. Maintenance: The Tenant shall pay the monthly society maintenance charge of Rs. 2,500 directly "
        "to the association.",
        "6. Lock-in: There is a lock-in period of two (2) months from the start date.",
        "7. Notice: After the lock-in period, either party may terminate this agreement by giving one (1) "
        "month's written notice to the other.",
        "8. Repairs: Minor day-to-day repairs such as replacing bulbs and tap washers shall be done by the "
        "Tenant. Structural repairs and repairs to appliances provided by the Owner shall be the Owner's "
        "responsibility.",
        "9. Renewal: The agreement may be renewed by mutual consent, with an increase of 5% on the monthly rent.",
        "10. Inspection: The Owner may inspect the premises at a reasonable time after giving at least 24 hours' "
        "prior notice to the Tenant.",
        "11. Use: The premises shall be used for residential purposes only and shall not be sublet.",
        "12. Utilities: Electricity and water charges as per meter readings shall be paid by the Tenant.",
    ],
    "typical-agreement": [
        PREMISES,
        "2. Term: This agreement is for eleven (11) months commencing from 1st December 2026.",
        "3. Rent: The monthly rent is Rs. 25,000 (Rupees Twenty Five Thousand only) including society "
        "maintenance, payable on or before the 5th of every month.",
        "4. Security Deposit: The Tenant has paid a security deposit of Rs. 1,50,000 (Rupees One Lakh Fifty "
        "Thousand only), which will be refunded without interest at the time of handing over possession after "
        "adjusting any dues.",
        "5. Lock-in: Both parties agree to a lock-in period of six (6) months. If the Tenant vacates during the "
        "lock-in period, the Tenant shall pay rent for the remaining lock-in months.",
        "6. Notice: After the lock-in period the Tenant shall give two (2) months' notice before vacating. The "
        "Owner may terminate this agreement by giving one (1) month's notice.",
        "7. Painting: At the time of vacating, the Tenant shall pay one month's rent towards painting charges, "
        "which shall be deducted from the security deposit.",
        "8. Renewal: On renewal the monthly rent shall be increased by 5%.",
        "9. Repairs: Minor repairs shall be borne by the Tenant. Major repairs shall be borne by the Owner.",
        "10. Inspection: The Owner may visit the premises at any reasonable time with prior intimation.",
        "11. Use: The premises shall be used for residential purposes only.",
        "12. Utilities: Electricity and water bills shall be paid by the Tenant as per actuals.",
    ],
    "risky-agreement": [
        PREMISES,
        "2. Term: This agreement is for a period of eleven (11) months commencing from 1st December 2026.",
        "3. Rent: The monthly rent is Rs. 40,000 (Rupees Forty Thousand only), payable in advance on or before "
        "the 1st of every month. Late payment of rent shall attract interest at 24% per annum.",
        "4. Security Deposit: The Tenant has paid a security deposit of Rs. 4,00,000 (Rupees Four Lakh only). "
        "The Owner may deduct from the deposit any amount as deemed fit by the Owner towards cleaning, painting, "
        "repairs and damages, and the balance, if any, shall be returned to the Tenant.",
        "5. Lock-in: The Tenant shall not vacate the premises before the expiry of eleven (11) months. If the "
        "Tenant vacates before the end of the lock-in period, the entire security deposit shall be forfeited.",
        "6. Notice: The Tenant shall give three (3) months' written notice before vacating. The Owner may ask "
        "the Tenant to vacate by giving fifteen (15) days' notice.",
        "7. Escalation: The monthly rent shall be increased by 15% on renewal of this agreement.",
        "8. Repairs: The Tenant shall bear the cost of all repairs to the premises, including plumbing, "
        "electrical and structural repairs, during the period of tenancy.",
        "9. Inspection: The Owner or his representatives may enter the premises at any time for inspection "
        "without prior notice to the Tenant.",
        "10. Guests: The Tenant shall not have guests staying overnight for more than two nights without the "
        "written permission of the Owner.",
        "11. Maintenance: The Tenant shall pay monthly maintenance of Rs. 4,000 and any one-time society "
        "charges levied during the tenancy.",
        "12. Use: The premises shall be used for residential purposes only.",
    ],
}


def build(name: str, clauses: list[str], out_dir: Path) -> Path:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10.5, leading=15, spaceAfter=8)
    title = ParagraphStyle("title", parent=styles["Title"], fontSize=16)
    path = out_dir / f"{name}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title=f"Sample {name}")
    story = [Paragraph("RENTAL AGREEMENT", title), Spacer(1, 6), Paragraph(PARTIES, body), Spacer(1, 4)]
    story += [Paragraph(c, body) for c in clauses]
    story += [Spacer(1, 18), Paragraph("Signed by the OWNER ____________ and the TENANT ____________ "
                                       "in the presence of two witnesses.", body)]
    doc.build(story)
    return path


if __name__ == "__main__":
    out = HERE
    for n, c in SAMPLES.items():
        print("wrote", build(n, c, out))
