from langfuse import observe, propagate_attributes

@observe(as_type="span", name="my_span")
def my_func():
    print("hello")

def test():
    with propagate_attributes(session_id="INC123"):
        my_func()

test()
