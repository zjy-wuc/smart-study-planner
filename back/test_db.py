from app.core.security import (
    create_access_token,
    decode_access_token,
)

# 模拟用户登录成功
token = create_access_token({
    "sub": "1"
})

print("Token created:", bool(token))

# 验证令牌
payload = decode_access_token(token)

print("Token valid:", payload is not None)
print("User ID:", payload["sub"] if payload else None)

# 测试错误令牌
wrong_payload = decode_access_token("invalid.token.value")

print("Wrong token:", wrong_payload)