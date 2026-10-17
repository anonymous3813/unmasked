from app.services.claim_detection_service import ClaimDetectionService

def main():
    test_analyze()

def test_analyze():
    cds = ClaimDetectionService()
    url = "https://www.amazon.com/AmazonBasics-Puresoft-PU-Padded-Mid-Back-Computer/dp/B081H3Y5NW/ref=sr_1_1_ffob_sspa?channelId=500&clpRedir=Y&dib=eyJ2IjoiMSJ9.YqIpplt5AiFtcN4Vm1HqTAccwFuW4hiKOKjYiaCWtIJ2WsNWEZWErmM4Zu4wxEY0RlINkN7JtHCc3Dtngv2eIPvYiu143PhnQHhQLFCI0uVe7s01As97QwHLuY407TKhiqdlHusBOFEnbT4qmwHVn-Q1doXvqpMHhh8mbzAZPIJmK32b8o10Ut3vgPKl9nA1wyF1OzFe1fhPCTeKezbd7RRuToUzzrooXtsMtea0mBPZ3Dd15YX-VVJ18BLuDXp8CrUuMcWksi0xI7kCUUCjdfLlr8oQ8etkckwbwmq_A0Q.j9C26Pd6eUJFBAwtpXHVhMTDzVURgheiQHAcxyKLZrk&dib_tag=se&keywords=desk%2Bchair&plpRedirect=mhFallback&qid=1792259709&sr=8-1-spons&sp_csd=d2lkZ2V0TmFtZT1zcF9hdGY&th=1"
    
    matches = cds.analyze_url(url)
    print(matches)

if __name__ == "__main__":
    main()