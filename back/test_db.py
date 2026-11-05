from app.core.security import hash_password, verify_password

password = "hello123"

# 注册时生成哈希
stored_hash = hash_password(password)

# 登录时验证
print(verify_password("hello123", stored_hash))
print(verify_password("wrong123", stored_hash))